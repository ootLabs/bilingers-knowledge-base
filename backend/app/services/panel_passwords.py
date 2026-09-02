"""Setting and changing panel passwords (T-82).

Split from `panel_auth` because it is a separate job with separate rules:
that module decides whether someone may get in, this one decides how a
credential is created or replaced. It builds on the session handling there
(a new password always ends other sessions) rather than duplicating it.

There is no self-service "forgot my password" flow, and that is deliberate:
the project has no mail path yet (see `docs/architecture.md`, open questions),
so such an endpoint would mint a token with no way to deliver it. Until mail
exists, an administrator issues the token and hands it over.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.panel import PanelPasswordReset, PanelUser
from app.security import hash_password, hash_token, new_token, verify_password
from app.services.panel_auth import (
    AuthenticationFailed,
    as_utc,
    revoke_all_sessions,
    utcnow,
)


class InvalidPasswordResetToken(Exception):
    """The token is unknown, already used, or past its expiry."""


def issue_password_reset(session: Session, user: PanelUser) -> tuple[PanelPasswordReset, str]:
    """Create a one-time token that lets its holder set this account's password.

    Any token issued earlier and still unused is expired first: two live tokens
    for one account means the older one keeps working after someone assumed
    they had replaced it.

    The caller commits. Both callers (creating an account, resetting a
    password) write more than this in the same transaction, and half of that
    landing would leave an account nobody can get into.
    """
    now = utcnow()
    _invalidate_outstanding_resets(session, user)

    token = new_token()
    reset = PanelPasswordReset(
        panel_user_id=user.id,
        token_hash=hash_token(token),
        expires_at=now + timedelta(hours=settings.panel_password_reset_ttl_hours),
    )
    session.add(reset)
    # Flushed, not just added: sessions run with autoflush off (see
    # `app.db.SessionLocal`), so an unflushed row is invisible to the query
    # above. Without this, issuing two tokens inside one transaction would
    # leave the first one live, which is exactly what this function exists to
    # prevent.
    session.flush()
    return reset, token

def _invalidate_outstanding_resets(session: Session, user: PanelUser) -> None:
    """Consume every reset token still live for this account.

    Marks `used_at` rather than pulling `expires_at` back to now: a token
    superseded this way reads in the audit trail as spent by something else,
    not as merely expired and never touched.
    """
    now = utcnow()
    outstanding = session.execute(
        select(PanelPasswordReset).where(
            PanelPasswordReset.panel_user_id == user.id,
            PanelPasswordReset.used_at.is_(None),
            PanelPasswordReset.expires_at > now,
        )
    ).scalars()
    for stale in outstanding:
        stale.used_at = now

def set_password_with_token(session: Session, *, token: str, new_password: str) -> PanelUser:
    """Spend a reset token and set the account's password.

    Every other session of that account is revoked. Whoever asked for a reset
    either forgot the password or suspects the account is compromised, and in
    the second case leaving old sessions alive would defeat the entire point.
    """
    now = utcnow()
    reset = session.execute(
        # Locked for the length of the transaction: reading `used_at` and then
        # writing it is a check-then-act, and two simultaneous confirmations of
        # the same token would otherwise both succeed, leaving the account with
        # whichever password arrived last. SQLite ignores the clause, which is
        # why the concurrency guarantee is PostgreSQL's alone.
        select(PanelPasswordReset)
        .where(PanelPasswordReset.token_hash == hash_token(token))
        .with_for_update()
    ).scalar_one_or_none()
    if reset is None or reset.used_at is not None or as_utc(reset.expires_at) <= now:
        raise InvalidPasswordResetToken("token is unknown, already used, or expired")

    user = session.get(PanelUser, reset.panel_user_id)
    if user is None or not user.is_active:  # pragma: no cover - cascade makes the first half dead
        raise InvalidPasswordResetToken("the account behind this token cannot be used")

    user.password_hash = hash_password(new_password)
    user.failed_login_count = 0
    user.locked_until = None
    reset.used_at = now
    revoke_all_sessions(session, user)
    session.commit()
    return user


def change_password(
    session: Session,
    *,
    user: PanelUser,
    current_password: str,
    new_password: str,
    keep_session_id: int | None = None,
) -> None:
    """Change your own password, proving you know the current one.

    Other sessions are revoked, the caller's own is kept: someone changing
    their password because they suspect it leaked needs the other sessions
    gone, and does not need to be thrown out of the tab they are sitting in.
    """
    if not verify_password(current_password, user.password_hash):
        raise AuthenticationFailed("current password does not match")

    user.password_hash = hash_password(new_password)
    revoke_all_sessions(session, user, except_session_id=keep_session_id)
    _invalidate_outstanding_resets(session, user)
    session.commit()
