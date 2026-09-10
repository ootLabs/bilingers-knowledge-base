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
from app.services.panel_columns import (
    IP_ADDRESS_LIMIT,
    USER_AGENT_LIMIT,
    normalise_email,
    truncated,
)
from app.services.panel_errors import unavailable_on_database_failure
from app.services.panel_login_audit import (
    LoginFailure,
    record_attempt,
    record_throttled_attempt,
)
from app.services.panel_two_factor import has_second_factor, verify_second_factor


class AuthenticationFailed(Exception):
    """The credentials do not identify an account that may log in."""


class SecondFactorRequired(Exception):
    """The password was right; this account also needs a code (T-83).

    The one refusal that is not answered generically, and deliberately so: it is
    only ever reached by somebody who already typed the correct password, so it
    reveals nothing they did not already know, and without it the form has no
    way to know it should ask for a code.
    """


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
    `populate_existing` is what makes the lock worth taking: without it
    SQLAlchemy hands back that identity-map object with the attributes it was
    loaded with and never looks at the row the lock just secured, so the
    increment would count from the value read before bcrypt ran and a
    concurrent attempt's increment would still be lost - the exact race this
    function exists to close (`expire_on_commit=False` in `app.db` means
    nothing expires the object in between either).

    The counter resets when the lock is applied rather than staying at the
    limit: after the lock expires the account gets a fresh run of attempts,
    instead of being locked again by the very next typo.
    """
    locked_row = session.execute(
        select(PanelUser)
        .where(PanelUser.id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one()
    locked_row.failed_login_count += 1
    if locked_row.failed_login_count >= settings.panel_login_max_attempts:
        locked_row.locked_until = utcnow() + timedelta(minutes=settings.panel_login_lockout_minutes)
        locked_row.failed_login_count = 0


@unavailable_on_database_failure
def login(
    session: Session,
    *,
    email: str,
    password: str,
    code: str | None = None,
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
        record_attempt(
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
        record_attempt(
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
        if user.is_active:
            # Only an account that could actually log in has anything for the
            # lockout to protect. Charging a deactivated one would let anybody
            # lock it with five requests, and `update_panel_user` does not clear
            # `locked_until` when it is switched back on, so its owner would
            # then be refused their own correct password by the lock check
            # above for the rest of it - the exact outcome the `is_active`
            # branch further down avoids for a *correct* password, undone here
            # for a wrong one. The reason recorded stays the real one either
            # way, so the audit trail still says somebody was guessing.
            _register_failure(session, user)
        record_attempt(
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
        # password. The wrong-password branch above skips the counter for a
        # deactivated account for that same reason.
        record_attempt(
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

    if has_second_factor(session, user):
        # Checked last, after the password and the account state, so a caller
        # who does not know the password cannot find out which accounts have
        # 2FA switched on.
        if not code:
            record_attempt(
                session,
                email=address,
                user=user,
                succeeded=False,
                reason=LoginFailure.SECOND_FACTOR_REQUIRED,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            session.commit()
            raise SecondFactorRequired(address)
        if not verify_second_factor(session, user, code):
            # Charged against the lockout exactly like a wrong password. Six
            # digits are guessable in a million tries, so a second factor with
            # no limit behind it would be a weaker factor, not a second one.
            _register_failure(session, user)
            record_attempt(
                session,
                email=address,
                user=user,
                succeeded=False,
                reason=LoginFailure.BAD_SECOND_FACTOR,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            session.commit()
            raise AuthenticationFailed("wrong second factor")

    token = new_token()
    panel_session = PanelSession(
        panel_user=user,
        token_hash=hash_token(token),
        expires_at=now + timedelta(minutes=settings.panel_session_ttl_minutes),
        ip_address=truncated(ip_address, IP_ADDRESS_LIMIT),
        user_agent=truncated(user_agent, USER_AGENT_LIMIT),
    )
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    session.add(panel_session)
    record_attempt(
        session,
        email=address,
        user=user,
        succeeded=True,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.commit()
    return panel_session, token
