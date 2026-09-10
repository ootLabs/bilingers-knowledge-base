"""Reading an uploaded .docx, without writing anything (T-85).

Its own prefix rather than `/api/panel/documents/imports`, and that is not
cosmetic: the documents router already owns `/api/panel/documents/{id}`, so a
literal segment underneath it would be matched as an id and answer 422 for a
word that is not a number.

This endpoint only reads. Keeping the parsed text is a normal save through the
documents router afterwards, so importing into an existing document is the same
new version as any other edit, never a duplicate document, and the editor gets
to see the result before any of it exists.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.dependencies import current_panel_user
from app.models.audit import AuditAction
from app.models.panel import PanelUser
from app.schemas.document_import import DocumentImportPreviewResponse
from app.services.docx_import import ImportedDocument, UnreadableDocument, read_document
from app.services.panel_audit import record_event

router = APIRouter(
    prefix="/api/panel/document-imports",
    tags=["panel"],
    responses={
        401: {"description": "No usable session token."},
        413: {"description": "The file is larger than the panel will read."},
        422: {"description": "Not a .docx, or nothing readable in it."},
    },
)

# Extension whitelist, server side. The browser's file picker filter is a
# convenience for the editor, not a control: anything can post to this endpoint.
_ALLOWED_SUFFIX = ".docx"


@router.post("", response_model=DocumentImportPreviewResponse)
async def preview_import(
    file: UploadFile = File(...),
    editor: PanelUser = Depends(current_panel_user),
    session: Session = Depends(get_session),
) -> ImportedDocument:
    """Read a .docx and answer with what was understood. Writes nothing.

    `async` because reading the upload genuinely is I/O and Starlette exposes
    it as such. The parse that follows is CPU work on a few megabytes at most,
    for a panel with a handful of accounts, so it runs inline rather than being
    pushed to a thread it does not need.

    The uploaded name is used for one thing only, checking the extension. It
    never becomes a path, and the bytes are parsed in memory.
    """
    name = (file.filename or "").lower()
    if not name.endswith(_ALLOWED_SUFFIX):
        raise HTTPException(status_code=422, detail="not_a_docx")

    limit = settings.docx_import_max_bytes
    # One byte past the limit is enough to know it is over it, and it means a
    # huge upload is never held in memory in full.
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status_code=413, detail="file_too_large")

    try:
        imported = read_document(data, max_bytes=limit)
    except UnreadableDocument as error:
        # `detail` is the reason key the service raised (`not_a_docx`,
        # `no_text_found`), so the frontend can say which of them it was.
        raise HTTPException(status_code=422, detail=str(error)) from error

    # Recorded even though nothing was saved: somebody put the foundation's
    # material into the system, and that is an access event whether or not the
    # preview is accepted (T-89). The size, not the name: a filename the caller
    # chose is not worth carrying into the journal.
    record_event(
        session,
        actor=editor,
        action=AuditAction.DOCUMENT_IMPORTED,
        detail=f"bytes={len(data)} headings={imported.heading_count}",
    )
    return imported
