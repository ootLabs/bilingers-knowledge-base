"""Managing panel accounts (T-82): the administrator's side of the panel.

Creating an account never sets a password. The administrator gets a one-time
token back and passes it to the person, who sets their own; nobody but the
owner ever knows an account's password, which also means an administrator
cannot act as an editor without leaving an obvious trail (a reset they issued
and a password the editor no longer knows).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.panel import PanelPasswordReset, PanelRole, PanelUser
from app.services.panel_auth import normalise_email, revoke_all_sessions
from app.services.panel_passwords import issue_password_reset


class EmailAlreadyUsed(Exception):
    """An account with that address exists. Deactivated ones count."""


class PanelUserNotFound(Exception):
    """No account with that identifier."""


class SelfManagementRefused(Exception):
    """An administrator tried to deactivate or demote their own account.

    The panel is expected to have one or two administrators, so this is the
    difference between a misclick and a panel nobody can administer any more,
    with no recovery path short of a database console.
    """


def create_panel_user(
    session: Session, *, email: str, role: PanelRole
) -> tuple[PanelUser, PanelPasswordReset, str]:
    """Create an account and return it with a one-time password setup token."""
    user = PanelUser(email=normalise_email(email), role=role, password_hash=None)
    try:
        # A SAVEPOINT, not the whole transaction: a duplicate address must undo
        # this insert and nothing else. Same reasoning as `app.services.chat`,
        # where a bare rollback would discard a caller's other pending work.
        with session.begin_nested():
            session.add(user)
            # Uniqueness is enforced by the database, not by a check-then-insert:
            # the check-then-insert races, the constraint does not.
            session.flush()
    except IntegrityError as error:
        raise EmailAlreadyUsed(email) from error

    reset, token = issue_password_reset(session, user)
    session.commit()
    return user, reset, token


def list_panel_users(session: Session) -> list[PanelUser]:
    """Every account, oldest first. No pagination: there are three to five."""
    return list(session.execute(select(PanelUser).order_by(PanelUser.id)).scalars())


def get_panel_user(session: Session, user_id: int) -> PanelUser:
    user = session.get(PanelUser, user_id)
    if user is None:
        raise PanelUserNotFound(str(user_id))
    return user


def update_panel_user(
    session: Session,
    *,
    actor: PanelUser,
    user_id: int,
    role: PanelRole | None = None,
    is_active: bool | None = None,
) -> PanelUser:
    """Change an account's role or activity. Deactivation ends its sessions.

    Revoking on deactivation is the whole point of the operation: an account
    that keeps a live session after being switched off has not been switched
    off. `resolve_session` re-checks `is_active` on every request as well, so
    the two together make it impossible to miss.
    """
    user = get_panel_user(session, user_id)

    if user.id == actor.id and (
        (is_active is False) or (role is not None and role is not PanelRole.ADMIN)
    ):
        raise SelfManagementRefused("an administrator cannot lock themselves out")

    if role is not None:
        user.role = role
    if is_active is not None:
        user.is_active = is_active
        if not is_active:
            revoke_all_sessions(session, user)

    session.commit()
    return user


def reset_password_for(
    session: Session, user_id: int
) -> tuple[PanelUser, PanelPasswordReset, str]:
    """Issue a fresh setup token for an account, invalidating any earlier one.

    Existing sessions are left alone on purpose: issuing a token is not proof
    that anything is wrong, and the sessions end the moment the token is
    actually spent (see `set_password_with_token`). Cutting access at the
    moment a token is printed would let a misdirected reset lock out someone
    who is working.
    """
    user = get_panel_user(session, user_id)
    reset, token = issue_password_reset(session, user)
    session.commit()
    return user, reset, token
