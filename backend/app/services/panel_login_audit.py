"""Recording every attempt to get into the panel (T-82).

Split from `app.services.panel_auth` when that file passed the size limit,
along the seam the log already named. That module decides whether a login
succeeds; this one writes down that it was tried, including for addresses that
match no account. A panel holding five accounts under an NDA has to be able to
answer "who tried" as well as "who got in", and T-89's journal reads these rows
rather than copying them.

The dependency runs one way: the login path imports this, never the reverse.
Nothing here reads an account, on purpose, so a refused attempt costs one
INSERT and no lookup.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.panel import PanelLoginAttempt, PanelUser
from app.services.panel_columns import (
    EMAIL_LIMIT,
    IP_ADDRESS_LIMIT,
    USER_AGENT_LIMIT,
    normalise_email,
    required,
    truncated,
)
from app.services.panel_errors import unavailable_on_database_failure


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
    IP_THROTTLED = "ip_throttled"
    SECOND_FACTOR_REQUIRED = "second_factor_required"
    BAD_SECOND_FACTOR = "bad_second_factor"


def record_attempt(
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
            # `required`, not `truncated`: the column is NOT NULL, and
            # `truncated` answers `None` for a blank, which would trade an
            # audit row for an IntegrityError on an unauthenticated endpoint.
            email=required(email, EMAIL_LIMIT),
            panel_user_id=user.id if user is not None else None,
            succeeded=succeeded,
            reason=reason,
            ip_address=truncated(ip_address, IP_ADDRESS_LIMIT),
            user_agent=truncated(user_agent, USER_AGENT_LIMIT),
        )
    )


@unavailable_on_database_failure
def record_throttled_attempt(
    session: Session,
    *,
    email: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Record that an attempt was turned away by the per-IP throttle.

    Without this, the requests refused before `login` runs leave no trace at
    all, and `panel_login_attempts` goes quiet exactly when it matters: a real
    flood would write at most one window's worth of rows and then nothing,
    which reads afterwards like the attack stopped.

    No account lookup, deliberately. This path exists to cost nothing, and
    which address was typed is already the row's `email`; a caller that
    wanted the account behind it can join on that later.

    The caller is being refused, so nothing else is pending on this session
    and committing here is safe.
    """
    record_attempt(
        session,
        email=normalise_email(email),
        user=None,
        succeeded=False,
        reason=LoginFailure.IP_THROTTLED,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.commit()
