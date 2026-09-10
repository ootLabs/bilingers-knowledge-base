"""The change journal as the panel reads it (T-89).

Read-only by construction: there is no request schema here, because there is no
endpoint that writes. Events are recorded as a side effect of the operations
they describe, never by a caller saying what happened.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditEntryResponse(BaseModel):
    """One journal line.

    `action` is a key (`document_published`, `login_failed`), not a sentence:
    the Polish that explains each one lives in the frontend dictionary. Same for
    `detail`, which carries the login audit's own reason values.
    """

    model_config = ConfigDict(from_attributes=True)

    occurred_at: datetime
    actor_email: str
    action: str
    subject_type: str | None
    subject_id: int | None
    detail: str | None
