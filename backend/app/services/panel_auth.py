"""Authentication for the foundation's panel (T-82).

Owns everything about proving who someone is: logging in, the session behind
every later request, logging out, and setting a password with a one-time token.
Managing other people's accounts is `app.services.panel_users`.

Two rules shape most of the code here:

* An attempt is recorded whether it succeeds or not, including for addresses
  that match no account. A panel with five accounts under an NDA has to be able
  to answer "who tried" as well as "who got in" (and T-89 builds on this row).
* A failure tells the caller as little as possible. Wrong password, unknown
  address, a locked account and one that was switched off are one answer with
  one timing: a caller who could tell them apart could enumerate which
  addresses have an account at all. Whether an account is locked is still
  visible, just not over HTTP - it is in `panel_login_attempts.reason` for
  whoever administers the panel.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.panel import PanelLoginAttempt, PanelSession, PanelUser
from app.security import hash_token, new_token, verify_password


class LoginFailure:
    """Why an attempt failed, as stored in `panel_login_attempts.reason`.

    Values, not an enum type in the database: see the column's comment in
    `app.models.panel`. They are audit detail only and are never returned to
    the client, which gets one generic answer instead.
    """

    UNKNOWN_ACCOUNT = "unknown_account"
    BAD_PASSWORD = "bad_password"
    NO_PASSWORD_SET = "no_password_set"
    INACTIVE_ACCOUNT = "inactive_account"
    LOCKED_ACCOUNT = "locked_account"


class AuthenticationFailed(Exception):
    """The credentials do not identify an account that may log in."""


def normalise_email(email: str) -> str:
    """Lowercase and strip, so one person cannot end up with two accounts.

    The local part of an address is case sensitive per RFC 5321, but no mail
    provider anyone here uses treats it that way, and two accounts differing
    only in capitalisation would be a genuine security problem in a panel where
    every account is known by name.
    """
    return email.strip().lower()


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """Attach UTC to a naive timestamp.

    Every timestamp in this schema is `TIMESTAMPTZ`, but a row created and read
    back inside one session still carries whatever the Python default produced,
    and comparing a naive datetime with an aware one raises rather than
    returning a wrong answer. Normalising on read keeps expiry checks total.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


_EMAIL_LIMIT = 320
_IP_ADDRESS_LIMIT = 45
_USER_AGENT_LIMIT = 255


def _truncated(value: str | None, limit: int) -> str | None:
    """Cut a value to what its column holds, keyed by this one function so a
    limit only ever has to be gotten right in one place, not wherever a
    caller happens to build the row."""
    return value[:limit] if value else None


def _record_attempt(
    session: Session,
    *,
    email: str,
    user: PanelUser | None,
    succeeded: bool,
    reason: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    # Truncated to what the columns hold. An over-long header is either a
    # bloated client or somebody probing, and neither deserves a 500 in place
    # of an audit row. Every caller gets this, not just the one router that
    # happens to trim the value on its way in.
    session.add(
        PanelLoginAttempt(
            email=_truncated(email, _EMAIL_LIMIT),
            panel_user_id=user.id if user is not None else None,
            succeeded=succeeded,
            reason=reason,
            ip_address=_truncated(ip_address, _IP_ADDRESS_LIMIT),
            user_agent=_truncated(user_agent, _USER_AGENT_LIMIT),
        )
    )


def find_by_email(session: Session, email: str) -> PanelUser | None:
    return session.execute(
        select(PanelUser).where(PanelUser.email == normalise_email(email))
    ).scalar_one_or_none()


def _register_failure(session: Session, user: PanelUser) -> None:
    """Count one failure against an account and lock it once the limit is hit.

    Re-reads the row `FOR UPDATE` first: two concurrent bad-password attempts
    against the same account must not both read the same `failed_login_count`
    and lose one increment. Locked only for this short write, not for the
    bcrypt comparison that already ran before the caller decided a failure
    needs registering - holding the lock across ~250ms of CPU would serialise
    concurrent *legitimate* logins on the same account for no reason.

    The re-select returns the same object `user` already refers to (same
    Session, same primary key, SQLAlchemy's identity map), so mutating it
    here is exactly as visible to the caller as mutating `user` directly.

    The counter resets when the lock is applied rather than staying at the
    limit: after the lock expires the account gets a fresh run of attempts,
    instead of being locked again by the very next typo.
    """
    locked_row = session.execute(
        select(PanelUser).where(PanelUser.id == user.id).with_for_update()
    ).scalar_one()
    locked_row.failed_login_count += 1
    if locked_row.failed_login_count >= settings.panel_login_max_attempts:
        locked_row.locked_until = utcnow() + timedelta(minutes=settings.panel_login_lockout_minutes)
        locked_row.failed_login_count = 0


def login(
    session: Session,
    *,
    email: str,
    password: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[PanelSession, str]:
    """Verify credentials and open a session. Returns the row and its token.

    The token is returned here and nowhere else: only its hash is stored, so
    this is the one moment it exists in readable form.

    Every exit path commits, because the login attempt and the lockout counter
    are as much a part of a failed login as the exception is. Rolling those
    back on failure would make the brute-force limit unenforceable.
    """
    address = normalise_email(email)
    user = find_by_email(session, address)
    now = utcnow()

    # Paid once, right here, no matter what turns out to be wrong with the
    # account: a locked or deactivated account must not answer measurably
    # faster than a wrong password, which is what makes every branch below
    # safe to answer with the same 401.
    password_ok = verify_password(password, user.password_hash if user else None)

    if user is None:
        _record_attempt(
            session,
            email=address,
            user=None,
            succeeded=False,
            reason=LoginFailure.UNKNOWN_ACCOUNT,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        session.commit()
        raise AuthenticationFailed("no such account")

    if user.locked_until is not None and as_utc(user.locked_until) > now:
        # Deliberately does not extend the lock: an attacker hammering a locked
        # account would otherwise keep the real owner out indefinitely. The
        # failure is the same generic one as a wrong password: a distinct
        # status here would tell an anonymous caller which addresses have an
        # account after a handful of requests.
        _record_attempt(
            session,
            email=address,
            user=user,
            succeeded=False,
            reason=LoginFailure.LOCKED_ACCOUNT,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        session.commit()
        raise AuthenticationFailed("account temporarily locked")

    if not password_ok:
        _register_failure(session, user)
        _record_attempt(
            session,
            email=address,
            user=user,
            succeeded=False,
            reason=(
                LoginFailure.NO_PASSWORD_SET
                if not user.has_password
                else LoginFailure.BAD_PASSWORD
            ),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        session.commit()
        raise AuthenticationFailed("wrong password")

    if not user.is_active:
        # Checked after the password on purpose: answering before it would let
        # anyone probe which addresses have deactivated accounts for free. Not
        # counted as a failure: the password was right, so this is not
        # evidence of guessing, and charging it against the lockout would
        # leave a reactivated account still locked out on its own correct
        # password.
        _record_attempt(
            session,
            email=address,
            user=user,
            succeeded=False,
            reason=LoginFailure.INACTIVE_ACCOUNT,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        session.commit()
        raise AuthenticationFailed("account is not active")

    token = new_token()
    panel_session = PanelSession(
        panel_user=user,
        token_hash=hash_token(token),
        expires_at=now + timedelta(minutes=settings.panel_session_ttl_minutes),
        ip_address=_truncated(ip_address, _IP_ADDRESS_LIMIT),
        user_agent=_truncated(user_agent, _USER_AGENT_LIMIT),
    )
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    session.add(panel_session)
    _record_attempt(
        session,
        email=address,
        user=user,
        succeeded=True,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.commit()
    return panel_session, token


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
