"""Reading the panel's change journal (T-89).

One verb, and it is `GET`. There is no endpoint here that writes, edits or
deletes a journal line, including for an administrator: a journal its own
subject can edit is not evidence of anything, and the cheapest way to guarantee
that is not to build the verb.

Administrators only. This is the answer to the foundation's question about
security (the call on 11.08), and it names who did what: an editor does not need
to read her colleagues' movements to write a document, and the addresses in here
are personal data with an unsettled retention policy (B-07).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.dependencies import require_admin
from app.models.panel import PanelUser
from app.schemas.panel_audit import AuditEntryResponse
from app.services.panel_audit import DEFAULT_LIMIT, MAX_LIMIT, AuditEntry, list_events

router = APIRouter(
    prefix="/api/panel/audit-events",
    tags=["panel"],
    responses={
        401: {"description": "No usable session token."},
        403: {"description": "Administrators only."},
        503: {"description": "The database is temporarily unavailable."},
    },
)


@router.get("", response_model=list[AuditEntryResponse])
def read_journal(
    actor_email: str | None = Query(default=None, max_length=320),
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    _admin: PanelUser = Depends(require_admin),
    session: Session = Depends(get_session),
) -> list[AuditEntry]:
    """The journal, newest first, narrowed by person and by date range.

    Both filters are optional and both are applied to the login audit as well as
    to the events table, so "everything this address did last week" is one
    answer rather than two lists to reconcile by hand.
    """
    return list_events(
        session, actor_email=actor_email, since=since, until=until, limit=limit
    )
