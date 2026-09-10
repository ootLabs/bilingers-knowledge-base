"""What happens to a panel session after it exists: resolving and revoking it.

Split out of `app.services.panel_auth` when the second factor (T-83) pushed
that file well past the size limit. The seam is the one that was already there:
`panel_auth` decides whether somebody may have a session, and this decides
whether a session they already hold still works.

Depends on `panel_auth` for the shared time helpers and never the other way
round: logging in does not revoke anything.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.panel import PanelSession, PanelUser
from app.security import hash_token
from app.services.panel_auth import as_utc, utcnow
from app.services.panel_errors import unavailable_on_database_failure


@unavailable_on_database_failure
def resolve_session(session: Session, token: str) -> tuple[PanelUser, PanelSession] | None:
    """Return the account behind a session token, or None if it cannot be used.

    None covers every reason equally: unknown token, revoked, expired, or an
    account deactivated since it logged in. The caller turns all of them into
    the same 401, because the difference is not the client's business.

    Deactivation is enforced here rather than only at logout time, so removing
    someone's access does not depend on their session being revoked correctly
    somewhere else.
    """
    row = session.execute(
        select(PanelSession, PanelUser)
        .join(PanelUser, PanelSession.panel_user_id == PanelUser.id)
        .where(PanelSession.token_hash == hash_token(token))
    ).one_or_none()
    if row is None:
        return None

    panel_session, user = row
    if panel_session.revoked_at is not None:
        return None
    if as_utc(panel_session.expires_at) <= utcnow():
        return None
    if not user.is_active:
        return None
    return user, panel_session


@unavailable_on_database_failure
def revoke_session(session: Session, panel_session: PanelSession) -> None:
    """Log out. Idempotent: revoking an already revoked session keeps the
    original timestamp, so the audit trail says when access actually ended."""
    if panel_session.revoked_at is None:
        panel_session.revoked_at = utcnow()
    session.commit()


def revoke_all_sessions(
    session: Session, user: PanelUser, *, except_session_id: int | None = None
) -> int:
    """Revoke every live session of an account. Returns how many were closed.

    Used wherever access has to stop everywhere at once: a password change, a
    reset, a deactivation. `except_session_id` keeps the caller's own session
    alive when they are changing their own password, so the sensible action
    does not log the person out of the tab they are working in.
    """
    now = utcnow()
    live = session.execute(
        select(PanelSession).where(
            PanelSession.panel_user_id == user.id,
            PanelSession.revoked_at.is_(None),
        )
    ).scalars()
    revoked = 0
    for panel_session in live:
        if except_session_id is not None and panel_session.id == except_session_id:
            continue
        panel_session.revoked_at = now
        revoked += 1
    return revoked
