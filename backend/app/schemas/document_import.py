"""What the panel gets back after reading a .docx, before anything is saved.

A preview, not a write. The editor sees what the system understood and decides
whether it is worth keeping, which is the only defence against a misread file
quietly becoming a draft in the knowledge base.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SkippedItemResponse(BaseModel):
    """One thing the reader left out, with how many times it happened.

    `reason` is a key (`unreadable_paragraph`, `table_not_imported`), not a
    sentence: the Polish explaining it to the editor lives in the frontend.
    """

    model_config = ConfigDict(from_attributes=True)

    reason: str
    count: int


class DocumentImportPreviewResponse(BaseModel):
    """The whole report: what came through, and what did not."""

    model_config = ConfigDict(from_attributes=True)

    title: str
    content: str
    heading_count: int
    paragraph_count: int
    skipped: list[SkippedItemResponse]
