"""Publishing a version and taking it back (T-88).

Split from `panel_documents.py` when that file passed the size limit, along the
same seam as the services underneath: everything there writes drafts and can
never change what a parent is reading, everything here is exactly the decision
to change it. Same prefix, because these are still operations on a document, and
FastAPI matches on the whole path, so the two routers cannot collide.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.dependencies import current_panel_user
from app.models.audit import AuditAction
from app.models.panel import PanelUser
from app.schemas.documents import DocumentVersionDetailResponse
from app.services.document_publishing import (
    NotPublished,
    PublicationConflict,
    publish_version,
    withdraw_version,
)
from app.services.documents import DocumentNotFound, VersionDetail, VersionNotFound
from app.services.panel_audit import record_event

router = APIRouter(
    prefix="/api/panel/documents",
    tags=["panel"],
    responses={
        401: {"description": "No usable session token."},
        404: {"description": "No such document, or no such version of it."},
        409: {"description": "The version is not in a state this action applies to."},
        503: {"description": "The database is temporarily unavailable."},
    },
)


def _not_found(error: Exception) -> HTTPException:
    detail = "version_not_found" if isinstance(error, VersionNotFound) else "document_not_found"
    return HTTPException(status_code=404, detail=detail)


@router.post(
    "/{document_id}/versions/{version_number}/publish",
    response_model=DocumentVersionDetailResponse,
)
def publish(
    document_id: int,
    version_number: int,
    editor: PanelUser = Depends(current_panel_user),
    session: Session = Depends(get_session),
) -> VersionDetail:
    """Put this version in front of parents. This is what "in the base" means.

    200 rather than 201: nothing is created that the caller did not already
    have, the version changes state. Publishing the version that is already
    published does nothing and still answers 200, so a second click from
    somebody who missed the first is harmless rather than an error.
    """
    try:
        published = publish_version(
            session, document_id=document_id, version_number=version_number, actor=editor
        )
    except (DocumentNotFound, VersionNotFound) as error:
        raise _not_found(error) from error
    except PublicationConflict as error:
        raise HTTPException(status_code=409, detail="publication_conflict") from error

    record_event(
        session,
        actor=editor,
        action=AuditAction.DOCUMENT_PUBLISHED,
        subject_type="document",
        subject_id=document_id,
        detail=f"version {version_number}",
    )
    return published


@router.post(
    "/{document_id}/versions/{version_number}/withdraw",
    response_model=DocumentVersionDetailResponse,
)
def withdraw(
    document_id: int,
    version_number: int,
    editor: PanelUser = Depends(current_panel_user),
    session: Session = Depends(get_session),
) -> VersionDetail:
    """Take this version back out of what the assistant may answer from."""
    try:
        withdrawn = withdraw_version(
            session, document_id=document_id, version_number=version_number
        )
    except (DocumentNotFound, VersionNotFound) as error:
        raise _not_found(error) from error
    except NotPublished as error:
        raise HTTPException(status_code=409, detail="not_published") from error

    # The row keeps who published it; who took it down is only answerable here,
    # which is why the journal records the actor for this one.
    record_event(
        session,
        actor=editor,
        action=AuditAction.DOCUMENT_WITHDRAWN,
        subject_type="document",
        subject_id=document_id,
        detail=f"version {version_number}",
    )
    return withdrawn
