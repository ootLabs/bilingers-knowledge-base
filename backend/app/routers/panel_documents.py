"""HTTP layer for the knowledge base's documents.

Guarded by `current_panel_user`, not `require_admin`: writing the knowledge
base is the editor's whole job, and an administrator role that also had to be
granted for it would mean every editor is an administrator (T-82 split the two
roles precisely so they are not).

There is no PUT and no DELETE on a version. That is not an oversight, it is the
model: a version is a snapshot, editing one means adding the next, and removing
one would destroy the trail that makes a bad answer explainable. The verbs
missing here are the card.

`detail` is a key, never a sentence. The Polish copy that answers each of them
lives in `frontend/lib/i18n/locales/pl.ts`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.dependencies import current_panel_user
from app.models.audit import AuditAction
from app.models.panel import PanelUser
from app.schemas.documents import (
    DocumentContentRequest,
    DocumentDetailResponse,
    DocumentSummaryResponse,
    DocumentVersionDetailResponse,
    DocumentVersionSummaryResponse,
    VersionRestoreRequest,
)
from app.services.document_queries import (
    get_document,
    get_version,
    list_documents,
    list_versions,
)
from app.services.documents import (
    ConcurrentEdit,
    DocumentDetail,
    DocumentNotFound,
    DocumentSummary,
    VersionDetail,
    VersionNotFound,
    VersionSummary,
    add_version,
    create_document,
    restore_version,
)
from app.services.panel_audit import record_event

router = APIRouter(
    prefix="/api/panel/documents",
    tags=["panel"],
    # Declared on the router, not per route: the 503 comes from the
    # `PanelServiceUnavailable` handler in `app.main` and can answer any of
    # them, and the 401 comes from the session dependency before a handler
    # body exists.
    responses={
        401: {"description": "No usable session token."},
        503: {"description": "The database is temporarily unavailable."},
    },
)

_NOT_FOUND = {404: {"description": "No such document, or no such version of it."}}
_CONFLICT = {409: {"description": "Another save took this version number first."}}


def _document_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="document_not_found")


def _version_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="version_not_found")


@router.get("", response_model=list[DocumentSummaryResponse])
def list_all(
    _editor: PanelUser = Depends(current_panel_user),
    session: Session = Depends(get_session),
) -> list[DocumentSummary]:
    """Every document with its newest version. No pagination yet: the
    foundation's base is tens of documents, not thousands, and a page control
    on a list of twelve is a control that only gets in the way."""
    return list_documents(session)


@router.post("", response_model=DocumentDetailResponse, status_code=201)
def create(
    payload: DocumentContentRequest,
    editor: PanelUser = Depends(current_panel_user),
    session: Session = Depends(get_session),
) -> DocumentDetail:
    """A new document and its first version, as a draft.

    The author is the account behind the token, never a field in the body: a
    caller must not be able to sign somebody else's name to a change the
    journal will later be read from (T-89).
    """
    created = create_document(
        session,
        author=editor,
        title=payload.title,
        content=payload.content,
        change_comment=payload.change_comment,
    )
    # After the operation committed, never before, and unable to fail it: the
    # editor gets her document whether or not the journal line landed (T-89).
    record_event(
        session,
        actor=editor,
        action=AuditAction.DOCUMENT_CREATED,
        subject_type="document",
        subject_id=created.id,
    )
    return created


@router.get("/{document_id}", response_model=DocumentDetailResponse, responses=_NOT_FOUND)
def read_one(
    document_id: int,
    _editor: PanelUser = Depends(current_panel_user),
    session: Session = Depends(get_session),
) -> DocumentDetail:
    """One document with the text of its newest version."""
    try:
        return get_document(session, document_id)
    except (DocumentNotFound, VersionNotFound) as error:
        raise _document_not_found() from error


@router.get(
    "/{document_id}/versions",
    response_model=list[DocumentVersionSummaryResponse],
    responses=_NOT_FOUND,
)
def read_history(
    document_id: int,
    _editor: PanelUser = Depends(current_panel_user),
    session: Session = Depends(get_session),
) -> list[VersionSummary]:
    """The document's history, newest first."""
    try:
        return list_versions(session, document_id)
    except DocumentNotFound as error:
        raise _document_not_found() from error


@router.get(
    "/{document_id}/versions/{version_number}",
    response_model=DocumentVersionDetailResponse,
    responses=_NOT_FOUND,
)
def read_version(
    document_id: int,
    version_number: int,
    _editor: PanelUser = Depends(current_panel_user),
    session: Session = Depends(get_session),
) -> VersionDetail:
    """One version with its text, for a preview or a comparison."""
    try:
        return get_version(session, document_id, version_number)
    except DocumentNotFound as error:
        raise _document_not_found() from error
    except VersionNotFound as error:
        raise _version_not_found() from error


@router.post(
    "/{document_id}/versions",
    response_model=DocumentVersionDetailResponse,
    status_code=201,
    responses=_NOT_FOUND | _CONFLICT,
)
def save_edit(
    document_id: int,
    payload: DocumentContentRequest,
    editor: PanelUser = Depends(current_panel_user),
    session: Session = Depends(get_session),
) -> VersionDetail:
    """Save an edit as a new version. 201, because a row is created.

    Always a draft, whatever the previous version's status was: saving must
    never change what the assistant serves.
    """
    try:
        version = add_version(
            session,
            document_id=document_id,
            author=editor,
            title=payload.title,
            content=payload.content,
            change_comment=payload.change_comment,
        )
        record_event(
            session,
            actor=editor,
            action=AuditAction.DOCUMENT_VERSION_SAVED,
            subject_type="document",
            subject_id=document_id,
            detail=f"version {version.version_number}",
        )
        return version
    except DocumentNotFound as error:
        raise _document_not_found() from error
    except ConcurrentEdit as error:
        # 409, not 503: nothing is broken, somebody else simply saved first.
        # The frontend keeps the text on screen, so the answer is retry, not
        # "your work is gone".
        raise HTTPException(status_code=409, detail="concurrent_edit") from error


@router.post(
    "/{document_id}/versions/{version_number}/restore",
    response_model=DocumentVersionDetailResponse,
    status_code=201,
    responses=_NOT_FOUND | _CONFLICT,
)
def restore(
    document_id: int,
    version_number: int,
    payload: VersionRestoreRequest,
    editor: PanelUser = Depends(current_panel_user),
    session: Session = Depends(get_session),
) -> VersionDetail:
    """Copy an old version's text into a new one. The history keeps growing."""
    try:
        restored = restore_version(
            session,
            document_id=document_id,
            version_number=version_number,
            author=editor,
            change_comment=payload.change_comment,
        )
        record_event(
            session,
            actor=editor,
            action=AuditAction.DOCUMENT_VERSION_RESTORED,
            subject_type="document",
            subject_id=document_id,
            detail=f"version {version_number} to {restored.version_number}",
        )
        return restored
    except DocumentNotFound as error:
        raise _document_not_found() from error
    except VersionNotFound as error:
        raise _version_not_found() from error
    except ConcurrentEdit as error:
        raise HTTPException(status_code=409, detail="concurrent_edit") from error
