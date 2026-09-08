"""Publishing a version, and taking one back (T-88).

This is where the panel stops being a CMS with no consequences: D1 says the
assistant answers only from the foundation's base, and "is in the base" means
exactly "is the published version of a document".

Content is still immutable. `status`, `published_at`, `published_by_id` and
`knowledge_base_version_id` are the only columns anything ever updates, and
this module is the only thing that updates them. `app.services.documents` still
holds to writing nothing but INSERTs, so a save can never change what a parent
is reading.

The trap this card is really about: `document_versions_one_published_per_document`
is a partial unique index, not deferrable, so it is checked per statement.
Promoting a new version before demoting the old one raises `IntegrityError` no
matter that both writes are in one transaction. Hence the explicit flush
between the two, in that order.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentStatus, DocumentVersion
from app.models.knowledge import KnowledgeBaseVersion
from app.models.panel import PanelUser
from app.services.document_queries import get_version
from app.services.documents import DocumentNotFound, VersionDetail, VersionNotFound
from app.services.knowledge_index import IndexChange, record_index_change
from app.services.panel_errors import unavailable_on_database_failure


class NotPublished(Exception):
    """Asked to withdraw a version that is not the published one."""


class PublicationConflict(Exception):
    """Two publications collided. Nothing was half-applied; try again."""


def _locked_document(session: Session, document_id: int) -> Document:
    """Lock the document so two publications of it cannot interleave.

    `populate_existing` for the same reason as in `app.services.documents`:
    without it the identity map answers the second read with the object it
    already holds and the lock guards a value nobody re-read.
    """
    document = session.execute(
        select(Document)
        .where(Document.id == document_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if document is None:
        raise DocumentNotFound(str(document_id))
    return document


def _version_row(session: Session, document_id: int, version_number: int) -> DocumentVersion:
    version = session.execute(
        select(DocumentVersion)
        .where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.version_number == version_number,
        )
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if version is None:
        raise VersionNotFound(f"{document_id}/{version_number}")
    return version


def _next_knowledge_base_version(session: Session, version: DocumentVersion) -> KnowledgeBaseVersion:
    """Stamp this publication with a knowledge base version of its own.

    The latest row is locked first, which serialises publications of *different*
    documents too: they share this counter, and the document lock above says
    nothing about them. An empty table has no row to lock, so the very first two
    publications can still collide on the unique constraint; that surfaces as
    `PublicationConflict` and a second click gets it, which is a better trade
    than a table lock taken on every publish forever.
    """
    session.execute(
        select(KnowledgeBaseVersion)
        .order_by(KnowledgeBaseVersion.version.desc())
        .limit(1)
        .with_for_update()
    ).scalar_one_or_none()

    highest = session.execute(select(func.max(KnowledgeBaseVersion.version))).scalar()
    published_count = session.execute(
        select(func.count())
        .select_from(DocumentVersion)
        .where(DocumentVersion.status == DocumentStatus.PUBLISHED)
    ).scalar_one()

    return KnowledgeBaseVersion(
        version=(highest or 0) + 1,
        record_count=published_count,
        # The bytes that went in, so "is this the same content we published"
        # is answerable without keeping a second copy of it.
        source_checksum=hashlib.sha256(version.content.encode("utf-8")).hexdigest(),
    )


@unavailable_on_database_failure
def publish_version(
    session: Session,
    *,
    document_id: int,
    version_number: int,
    actor: PanelUser,
) -> VersionDetail:
    """Put one version in front of parents. All of it, or none of it.

    Publishing the version that is already published is not an error and does
    nothing: silence after a click is what makes an editor click again, and a
    second click must not become a second knowledge base version.
    """
    _locked_document(session, document_id)
    version = _version_row(session, document_id, version_number)

    if version.status is DocumentStatus.PUBLISHED:
        return get_version(session, document_id, version_number)

    current = session.execute(
        select(DocumentVersion)
        .where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.status == DocumentStatus.PUBLISHED,
        )
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()

    now = datetime.now(UTC)
    if current is not None:
        # Withdrawn, not back to draft: it was published, and pretending
        # otherwise would lose the fact that parents once read it.
        current.status = DocumentStatus.WITHDRAWN
        # The flush that makes this work at all. Without it SQLAlchemy is free
        # to emit the promotion first, and the partial unique index refuses two
        # published versions of one document mid-transaction.
        session.flush()

    version.status = DocumentStatus.PUBLISHED
    version.published_at = now
    version.published_by_id = actor.id
    try:
        session.flush()
        knowledge_base_version = _next_knowledge_base_version(session, version)
        session.add(knowledge_base_version)
        session.flush()
        version.knowledge_base_version_id = knowledge_base_version.id
        session.flush()
    except IntegrityError as error:
        # Nothing is half applied: the whole transaction goes back, including
        # the demotion above. `get_session` closes the session at the end of the
        # request, which rolls it back.
        raise PublicationConflict(str(document_id)) from error

    record_index_change(
        IndexChange.PUBLISHED,
        document_id=document_id,
        version_number=version_number,
        knowledge_base_version=knowledge_base_version.version,
    )
    session.commit()
    return get_version(session, document_id, version_number)


@unavailable_on_database_failure
def withdraw_version(
    session: Session, *, document_id: int, version_number: int
) -> VersionDetail:
    """Take a version back out of what the assistant may answer from.

    `knowledge_base_version_id` stays where it is. It records which ingest this
    text belonged to while it was live, and an answer given last week still
    needs to be traceable to it.

    Takes no actor, and that is deliberate: `published_by_id` has one meaning,
    who put this in front of parents, and overwriting it with whoever pulled the
    text back would lose that. Who withdrew it is the change journal's answer
    (T-89).
    """
    _locked_document(session, document_id)
    version = _version_row(session, document_id, version_number)

    if version.status is not DocumentStatus.PUBLISHED:
        raise NotPublished(f"{document_id}/{version_number}")

    version.status = DocumentStatus.WITHDRAWN
    session.flush()

    record_index_change(
        IndexChange.WITHDRAWN,
        document_id=document_id,
        version_number=version_number,
        knowledge_base_version=None,
    )
    session.commit()
    return get_version(session, document_id, version_number)
