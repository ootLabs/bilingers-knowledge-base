"""Writing a document: creating one, saving an edit, bringing an old text back.

Editing never means an UPDATE here. Every function inserts a row and leaves the
earlier ones byte for byte as they were, which is what makes a factual error
rollable back and a bad answer investigable later (T-37). Nothing in the
database enforces that (no trigger, no `updated_at` to bump), so this module is
the enforcement.

The one exception is not here: publication changes `status`, `published_at`,
`published_by_id` and `knowledge_base_version_id` on an existing row, and that
lives in `app.services.document_publishing` alone. Saving an edit still cannot
change what a parent is reading.

Reading documents back is `app.services.document_queries`, split off when this
file passed the size limit. The exceptions and view shapes stay here, because
both halves raise and build them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentStatus, DocumentVersion
from app.models.panel import PanelUser
from app.services.panel_errors import unavailable_on_database_failure

# The constraint a save races against. Named rather than matched by substring,
# so a future constraint on this table cannot be misreported to an editor as
# somebody else's simultaneous save.
_VERSION_NUMBER_CONSTRAINT = "document_versions_document_id_version_number_key"


class DocumentNotFound(Exception):
    """No document with that identifier."""


class VersionNotFound(Exception):
    """The document exists, that version number does not."""


class ConcurrentEdit(Exception):
    """Another save took the version number this one was writing.

    Nothing is lost and nothing is merged: the text never reached the database,
    so the screen still holds it and the editor decides (T-87 requires that).
    """


@dataclass(frozen=True)
class VersionSummary:
    """One version as a list shows it: everything except the content.

    Flat, with people already resolved to addresses, because `DocumentVersion`
    has no relationship to `panel_users` (only the two foreign keys).
    """

    version_number: int
    status: DocumentStatus
    title: str
    change_comment: str | None
    author_email: str | None
    created_at: datetime
    # Both null until the version is published (T-88), and kept apart from
    # `created_at`/`author_email` because a version written on Monday and
    # published on Friday by somebody else is the normal case.
    published_at: datetime | None
    published_by_email: str | None


@dataclass(frozen=True)
class VersionDetail(VersionSummary):
    """One version with its content, for the editor and the history preview."""

    content: str


@dataclass(frozen=True)
class DocumentSummary:
    """A document, its newest version, and whichever version is published.

    Both, because they answer different questions and stop being the same row
    at the first save. Reporting only the newest one made the panel claim
    nothing was published while parents went on reading the older version that
    still was. `None` means nothing ever went live; it is never more than one,
    which `document_versions_one_published_per_document` guarantees.
    """

    id: int
    created_at: datetime
    latest_version: VersionSummary
    published_version: VersionSummary | None = None


@dataclass(frozen=True)
class DocumentDetail:
    """A document opened for editing: identity plus the newest version's text.

    `published_version` is a summary, not a detail: the editor says which
    version parents are reading, it does not show its text. Comparing the two
    is the history screen's job.
    """

    id: int
    created_at: datetime
    latest_version: VersionDetail
    published_version: VersionSummary | None = None


def summary_of(
    version: DocumentVersion, author_email: str | None, publisher_email: str | None = None
) -> VersionSummary:
    return VersionSummary(
        version_number=version.version_number,
        status=version.status,
        title=version.title,
        change_comment=version.change_comment,
        author_email=author_email,
        created_at=version.created_at,
        published_at=version.published_at,
        published_by_email=publisher_email,
    )


def detail_of(
    version: DocumentVersion, author_email: str | None, publisher_email: str | None = None
) -> VersionDetail:
    """The same fields plus the content, built from `summary_of` rather than
    listing all eight again: two copies of one field list is one place for the
    next field to be added and the other to be forgotten."""
    return VersionDetail(
        **asdict(summary_of(version, author_email, publisher_email)),
        content=version.content,
    )


def require_document(session: Session, document_id: int) -> Document:
    document = session.get(Document, document_id)
    if document is None:
        raise DocumentNotFound(str(document_id))
    return document


@unavailable_on_database_failure
def create_document(
    session: Session,
    *,
    author: PanelUser,
    title: str,
    content: str,
    change_comment: str | None = None,
) -> DocumentDetail:
    """A new document and its version 1, both in one transaction.

    No numbering race to close: nothing else knows this document's id yet.
    """
    document = Document()
    session.add(document)
    session.flush()

    version = DocumentVersion(
        document_id=document.id,
        version_number=1,
        status=DocumentStatus.DRAFT,
        title=title,
        content=content,
        change_comment=change_comment,
        author_id=author.id,
    )
    session.add(version)
    session.commit()

    return DocumentDetail(
        id=document.id,
        created_at=document.created_at,
        latest_version=detail_of(version, author.email),
    )


def _next_version_number(session: Session, document_id: int) -> int:
    """The number this save will take, with the document row locked first.

    `SELECT ... FOR UPDATE` on `documents` is what serialises two saves of the
    same document: they cannot both read the same highest number and both try to
    write it. `populate_existing` is not decoration. Without it SQLAlchemy
    answers the second read out of its identity map with the object it already
    holds, never looks at the row the lock just secured, and the lock protects
    nothing (the trap the login counter hit in T-82).

    On SQLite `with_for_update` is ignored, so the race is only genuinely closed
    on PostgreSQL and only an `integration` test can prove it. The unique
    constraint is the backstop on both.
    """
    document = session.execute(
        select(Document)
        .where(Document.id == document_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if document is None:
        raise DocumentNotFound(str(document_id))

    highest = session.execute(
        select(func.max(DocumentVersion.version_number)).where(
            DocumentVersion.document_id == document_id
        )
    ).scalar()
    return (highest or 0) + 1


def _is_version_number_clash(error: IntegrityError) -> bool:
    """Whether this is two saves colliding, rather than some other rule.

    By constraint name where the driver reports one (PostgreSQL), by substring
    where it does not (SQLite). Same shape as `app.services.panel_users`.
    """
    constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
    if constraint is not None:
        return constraint == _VERSION_NUMBER_CONSTRAINT
    return "version_number" in str(error.orig).lower()


@unavailable_on_database_failure
def add_version(
    session: Session,
    *,
    document_id: int,
    author: PanelUser,
    title: str,
    content: str,
    change_comment: str | None = None,
) -> VersionDetail:
    """Save an edit as a new version. The only path by which text changes."""
    version = DocumentVersion(
        document_id=document_id,
        version_number=_next_version_number(session, document_id),
        # Always a draft, even when the version being superseded is published.
        # A save must never change what the assistant serves; that is a
        # separate, deliberate action (T-88).
        status=DocumentStatus.DRAFT,
        title=title,
        content=content,
        change_comment=change_comment,
        author_id=author.id,
    )
    try:
        # A SAVEPOINT rather than the whole transaction, matching
        # `create_panel_user`: a lost race must undo this insert and nothing
        # else the caller had pending.
        with session.begin_nested():
            session.add(version)
            session.flush()
    except IntegrityError as error:
        if not _is_version_number_clash(error):
            # Re-raised into the caller's decorator, which answers 503: the
            # boundary already validated the input, so an unexpected constraint
            # failure is the server being wrong, not the request.
            raise
        raise ConcurrentEdit(str(document_id)) from error

    session.commit()
    return detail_of(version, author.email)


@unavailable_on_database_failure
def restore_version(
    session: Session,
    *,
    document_id: int,
    version_number: int,
    author: PanelUser,
    change_comment: str | None = None,
) -> VersionDetail:
    """Bring an old version's text back as a new one. History never shortens.

    Copying forward rather than rewinding is the point: after restoring version
    1 of three there are four versions, not one, and what was undone is still
    readable. The copy is a draft like any other save.

    `change_comment` comes from the caller because "restored from version 1" is
    user-facing Polish, which `docs/conventions.md` keeps in the frontend.
    """
    require_document(session, document_id)
    source = session.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.version_number == version_number,
        )
    ).scalar_one_or_none()
    if source is None:
        raise VersionNotFound(f"{document_id}/{version_number}")

    # Straight through `add_version`, so a restore is a save like any other:
    # same numbering, same lock, same draft status, same refusal on a race.
    return add_version(
        session,
        document_id=document_id,
        author=author,
        title=source.title,
        content=source.content,
        change_comment=change_comment,
    )
