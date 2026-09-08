"""Request and response shapes for the panel's document endpoints.

Validated here rather than deeper in, per `docs/conventions.md`: the boundary
refuses bad input and everything past the router is assumed valid.

The control-character rule is the same one `app.schemas.panel` applies to an
address, moved one field along. A NUL byte in a title reaches psycopg as a bind
parameter, which refuses it, and the request then answers 500 with a traceback
for something the caller could plainly fix. 422 says so instead.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.document import DocumentStatus

# Everything a terminal would act on rather than print. Tab, newline and
# carriage return are excluded from the set: a document's body is prose with
# paragraphs in it, and banning line breaks there would ban the content itself.
_CONTROL_IN_TEXT = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# A title and a change comment are single lines. A newline in either is either
# a paste accident or someone trying to break a log line in half, and neither
# is worth accepting.
_CONTROL_IN_LINE = re.compile(r"[\x00-\x1f\x7f]")

# `documents.title` is VARCHAR(500). Matching the column exactly means an
# over-long title is refused as a 422 rather than truncated silently or
# rejected by the driver as a 500.
TITLE_MAX_LENGTH = 500
COMMENT_MAX_LENGTH = 500

Title = Annotated[str, Field(min_length=1, max_length=TITLE_MAX_LENGTH)]
Content = Annotated[str, Field(min_length=1)]
# No default in the `Field` here: Pydantic refuses one inside `Annotated`, so
# each field carries `= None` itself.
ChangeComment = Annotated[str | None, Field(max_length=COMMENT_MAX_LENGTH)]


def _reject_control_characters(value: str | None, pattern: re.Pattern[str]) -> str | None:
    if value is not None and pattern.search(value):
        raise ValueError("control characters are not allowed")
    return value


class DocumentContentRequest(BaseModel):
    """The text of one save: a new document, or a new version of one.

    Both endpoints take the same three fields because they write the same row.
    A separate schema per endpoint would be two places to keep one rule in.

    `str_strip_whitespace` so a title padded with spaces is measured after
    trimming, not before, and so a body of nothing but whitespace fails
    `min_length` instead of being stored as an empty document.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    title: Title
    content: Content
    change_comment: ChangeComment = None

    @field_validator("title", "change_comment")
    @classmethod
    def one_line_only(cls, value: str | None) -> str | None:
        return _reject_control_characters(value, _CONTROL_IN_LINE)

    @field_validator("content")
    @classmethod
    def printable_text(cls, value: str) -> str:
        return _reject_control_characters(value, _CONTROL_IN_TEXT)


class VersionRestoreRequest(BaseModel):
    """Optional note recorded against the version a restore creates.

    A body rather than nothing, because the sentence explaining what happened
    ("restored from version 1") is Polish copy and lives in the frontend.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    change_comment: ChangeComment = None

    @field_validator("change_comment")
    @classmethod
    def one_line_only(cls, value: str | None) -> str | None:
        return _reject_control_characters(value, _CONTROL_IN_LINE)


class DocumentVersionSummaryResponse(BaseModel):
    """One version without its text: enough for a list row or a history entry."""

    model_config = ConfigDict(from_attributes=True)

    version_number: int
    status: DocumentStatus
    title: str
    change_comment: str | None
    # People as addresses, not ids. The panel holds three to five accounts that
    # know each other by name, and an id on screen is exactly the technical
    # identifier T-86 rules out.
    author_email: str | None
    created_at: datetime
    # Both null until the version is published (T-88). The screen needs them
    # together: "opublikowany" with no date and no name is a claim, not an
    # answer.
    published_at: datetime | None
    published_by_email: str | None


class DocumentVersionDetailResponse(DocumentVersionSummaryResponse):
    """One version with its text, for the editor and the history preview."""

    content: str


class DocumentSummaryResponse(BaseModel):
    """A list row: the document plus whatever its newest version says."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    latest_version: DocumentVersionSummaryResponse


class DocumentDetailResponse(BaseModel):
    """A document opened for editing, with the newest version's text."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    latest_version: DocumentVersionDetailResponse
