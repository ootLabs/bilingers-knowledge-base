"""Writing and reading the panel's change journal (T-89).

Two rules, and the first one is the reason this module is careful rather than
short:

* Recording an event must never fail the operation it describes. If the journal
  write breaks, the editor still gets the result of what she did, and the
  failure goes to the server log. A panel that refuses to save a document
  because it could not write a log line is worse than a panel with a gap in its
  log line.
* The journal is read-only, for everybody. Nothing here updates or deletes a
  row, and no router exposes a verb that could. A journal its own subject can
  edit is not evidence of anything.

Reading merges two tables. `panel_login_attempts` (T-82) already records every
attempt to get in, including for addresses with no account behind them, so it
is read rather than copied: one fact, one row, in one place. What it does not
cover (logging out, and everything done to documents and accounts) is in
`panel_audit_events`. The union below is what makes them one list on screen.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.audit import AuditAction, PanelAuditEvent
from app.models.panel import PanelLoginAttempt, PanelUser
from app.services.panel_errors import unavailable_on_database_failure

logger = logging.getLogger(__name__)

# The journal is read newest first and never grows a page control per user: the
# panel has three to five accounts, so a cap is about not sending ten thousand
# rows to a browser, not about navigation.
DEFAULT_LIMIT = 200
MAX_LIMIT = 1000

_DETAIL_LIMIT = 255
_EMAIL_LIMIT = 320


@dataclass(frozen=True)
class AuditEntry:
    """One journal line, from whichever table it came from."""

    occurred_at: datetime
    actor_email: str
    action: str
    subject_type: str | None
    subject_id: int | None
    detail: str | None


def record_event(
    session: Session,
    *,
    actor: PanelUser,
    action: str,
    subject_type: str | None = None,
    subject_id: int | None = None,
    detail: str | None = None,
) -> None:
    """Note that something happened. Cannot fail the caller.

    Called after the operation it describes has already committed, so this
    commits a row of its own. A failure here is swallowed and logged: the
    person gets the result of their action, and the gap in the journal is
    visible in the server log rather than in a 500 they cannot act on.
    """
    try:
        session.add(
            PanelAuditEvent(
                actor_id=actor.id,
                actor_email=actor.email[:_EMAIL_LIMIT],
                action=action,
                subject_type=subject_type,
                subject_id=subject_id,
                detail=detail[:_DETAIL_LIMIT] if detail else None,
            )
        )
        session.commit()
    except SQLAlchemyError:
        # `exception` rather than `error`: without the traceback, a journal that
        # has quietly stopped recording looks exactly like a quiet week.
        logger.exception(
            "could not record audit event action=%s subject=%s/%s",
            action,
            subject_type,
            subject_id,
        )
        try:
            session.rollback()
        except SQLAlchemyError:
            # The reason this whole block exists is that the operation being
            # described has already committed, so nothing here may reach the
            # caller. A rollback on a connection that has just dropped raises
            # a second driver exception (the hazard `panel_errors` documents),
            # and unguarded it would turn a missing log line into a 500 for
            # work that actually succeeded.
            logger.exception("could not roll back after a failed audit write")


def _events_query() -> Select[tuple[datetime, str, str, str | None, int | None, str | None]]:
    return select(
        PanelAuditEvent.occurred_at.label("occurred_at"),
        PanelAuditEvent.actor_email.label("actor_email"),
        PanelAuditEvent.action.label("action"),
        PanelAuditEvent.subject_type.label("subject_type"),
        PanelAuditEvent.subject_id.label("subject_id"),
        PanelAuditEvent.detail.label("detail"),
    )


@unavailable_on_database_failure
def list_events(
    session: Session,
    *,
    actor_email: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[AuditEntry]:
    """The journal, newest first, optionally narrowed by person and by dates.

    Each source is filtered and capped in its own query, so both keep their own
    index; only the merge happens here. `since` and `until` arrive without a
    time zone (they come from date inputs), which the database reads in its own,
    UTC in this stack. Good enough for "show me last Tuesday"; anything that has
    to be exact to the hour should send an offset.
    """
    events = _events_query()
    logins = select(
        PanelLoginAttempt.attempted_at.label("occurred_at"),
        PanelLoginAttempt.email.label("actor_email"),
        PanelLoginAttempt.succeeded.label("succeeded"),
        PanelLoginAttempt.panel_user_id.label("subject_id"),
        PanelLoginAttempt.reason.label("detail"),
    )

    if actor_email is not None:
        needle = actor_email.strip().lower()
        events = events.where(PanelAuditEvent.actor_email == needle)
        logins = logins.where(PanelLoginAttempt.email == needle)
    if since is not None:
        events = events.where(PanelAuditEvent.occurred_at >= since)
        logins = logins.where(PanelLoginAttempt.attempted_at >= since)
    if until is not None:
        events = events.where(PanelAuditEvent.occurred_at <= until)
        logins = logins.where(PanelLoginAttempt.attempted_at <= until)

    capped = max(1, min(limit, MAX_LIMIT))

    entries = [
        AuditEntry(
            occurred_at=row.occurred_at,
            actor_email=row.actor_email,
            action=row.action,
            subject_type=row.subject_type,
            subject_id=row.subject_id,
            detail=row.detail,
        )
        for row in session.execute(events.order_by(PanelAuditEvent.occurred_at.desc()).limit(capped))
    ]
    entries.extend(
        AuditEntry(
            occurred_at=row.occurred_at,
            actor_email=row.actor_email,
            action=(
                AuditAction.LOGIN_SUCCEEDED if row.succeeded else AuditAction.LOGIN_FAILED
            ),
            subject_type="panel_user",
            subject_id=row.subject_id,
            detail=row.detail,
        )
        for row in session.execute(
            logins.order_by(PanelLoginAttempt.attempted_at.desc()).limit(capped)
        )
    )

    # Merged in Python rather than with a `UNION ALL`. The union would push the
    # sort and the limit into the database, which is the right shape once this
    # is large, but it needs the boolean `succeeded` turned into an action name
    # by a `CASE` inside the query, and each side capped separately anyway to
    # keep its own index. For a panel with five accounts, two capped reads and a
    # sort of at most 2000 rows is the honest version; revisit when the journal
    # outgrows a screenful, not before.
    entries.sort(key=lambda entry: entry.occurred_at, reverse=True)
    return entries[:capped]
