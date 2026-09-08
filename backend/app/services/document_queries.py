"""Reading documents back: the list, one document, its history, one version.

Split from `app.services.documents` when that file passed the size limit, along
the seam that was already there: everything here reads and nothing writes. The
exceptions and the view shapes stay in `documents`, so this module depends on
it and never the other way round.
"""

from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, aliased

from app.models.document import Document, DocumentVersion
from app.models.panel import PanelUser
from app.services.documents import (
    DocumentDetail,
    DocumentSummary,
    VersionDetail,
    VersionNotFound,
    VersionSummary,
    detail_of,
    require_document,
    summary_of,
)
from app.services.panel_errors import unavailable_on_database_failure

# Two joins to the same table, so two aliases. Module level, because the alias
# in the SELECT list and the one in the JOIN have to be the same object.
_AUTHOR = aliased(PanelUser)
_PUBLISHER = aliased(PanelUser)


def _versions_with_people() -> Select[tuple[DocumentVersion, str | None, str | None]]:
    """Versions with the address of whoever wrote and whoever published them.

    Outer joins, because both foreign keys are `ON DELETE SET NULL`: content has
    to outlive the account that wrote it (T-84), so a version whose author was
    deleted is still listed, just with nobody's name against it.
    """
    return (
        select(DocumentVersion, _AUTHOR.email, _PUBLISHER.email)
        .outerjoin(_AUTHOR, _AUTHOR.id == DocumentVersion.author_id)
        .outerjoin(_PUBLISHER, _PUBLISHER.id == DocumentVersion.published_by_id)
    )


@unavailable_on_database_failure
def list_documents(session: Session) -> list[DocumentSummary]:
    """Every document with its newest version, in one query.

    One query, not one per document: this list is the screen the editor lands
    on, and a loop over documents makes it N plus 1 the moment the foundation
    has more than a handful.

    A window function rather than `DISTINCT ON`, which is PostgreSQL only. The
    panel's behaviour tests run on SQLite (`panel_db`, see
    `backend/tests/conftest.py`), so a PostgreSQL-only shape would push the
    query-count test into `integration` and out of the run an agent does after
    every edit. `row_number()` works on both.

    An inner join, so a document with no versions never appears. Nothing can
    create one: `create_document` writes the document and its first version in a
    single transaction.
    """
    ranked = select(
        DocumentVersion.id.label("version_id"),
        func.row_number()
        .over(
            partition_by=DocumentVersion.document_id,
            order_by=DocumentVersion.version_number.desc(),
        )
        .label("position"),
    ).subquery()

    rows = session.execute(
        select(Document, DocumentVersion, _AUTHOR.email, _PUBLISHER.email)
        .join(DocumentVersion, DocumentVersion.document_id == Document.id)
        .join(ranked, ranked.c.version_id == DocumentVersion.id)
        .outerjoin(_AUTHOR, _AUTHOR.id == DocumentVersion.author_id)
        .outerjoin(_PUBLISHER, _PUBLISHER.id == DocumentVersion.published_by_id)
        .where(ranked.c.position == 1)
        # Newest change first: the list answers "what moved lately", and the id
        # breaks ties so two saves in the same second do not order themselves
        # differently on every request.
        .order_by(DocumentVersion.created_at.desc(), Document.id.desc())
    ).all()

    return [
        DocumentSummary(
            id=document.id,
            created_at=document.created_at,
            latest_version=summary_of(version, author_email, publisher_email),
        )
        for document, version, author_email, publisher_email in rows
    ]


@unavailable_on_database_failure
def get_document(session: Session, document_id: int) -> DocumentDetail:
    """One document with the text of its newest version."""
    document = require_document(session, document_id)
    row = session.execute(
        _versions_with_people()
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    ).first()
    if row is None:
        raise VersionNotFound(str(document_id))
    version, author_email, publisher_email = row
    return DocumentDetail(
        id=document.id,
        created_at=document.created_at,
        latest_version=detail_of(version, author_email, publisher_email),
    )


@unavailable_on_database_failure
def list_versions(session: Session, document_id: int) -> list[VersionSummary]:
    """The document's history, newest first. It only ever grows."""
    require_document(session, document_id)
    rows = session.execute(
        _versions_with_people()
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_number.desc())
    ).all()
    return [
        summary_of(version, author_email, publisher_email)
        for version, author_email, publisher_email in rows
    ]


@unavailable_on_database_failure
def get_version(session: Session, document_id: int, version_number: int) -> VersionDetail:
    """One version with its text, for a preview or a comparison."""
    require_document(session, document_id)
    row = session.execute(
        _versions_with_people().where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.version_number == version_number,
        )
    ).first()
    if row is None:
        raise VersionNotFound(f"{document_id}/{version_number}")
    version, author_email, publisher_email = row
    return detail_of(version, author_email, publisher_email)
