"""HTTP layer for account management. Administrators only.

Everything here is one administrator acting on somebody else's account:
creating it, changing its role, switching it off, issuing a password token.
Acting on your own account is `panel_auth.py`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.dependencies import require_admin
from app.models.panel import PanelUser
from app.schemas.panel import (
    PanelUserCreateRequest,
    PanelUserResponse,
    PanelUserUpdateRequest,
    PasswordResetResponse,
)
from app.services.panel_users import (
    EmailAlreadyUsed,
    PanelUserNotFound,
    SelfManagementRefused,
    create_panel_user,
    list_panel_users,
    reset_password_for,
    update_panel_user,
)

router = APIRouter(prefix="/api/panel/users", tags=["panel"])


@router.get("", response_model=list[PanelUserResponse])
def list_users(
    _admin: PanelUser = Depends(require_admin),
    session: Session = Depends(get_session),
) -> list[PanelUser]:
    """Every account. Three to five rows, so no pagination."""
    return list_panel_users(session)


@router.post(
    "",
    response_model=PasswordResetResponse,
    status_code=201,
    responses={409: {"description": "An account with that address already exists."}},
)
def create_user(
    payload: PanelUserCreateRequest,
    _admin: PanelUser = Depends(require_admin),
    session: Session = Depends(get_session),
) -> PasswordResetResponse:
    """Create an account. There is no registration form; this is the only way.

    The response carries a one-time setup token, not a password: the
    administrator passes it on, and the account's owner chooses the password
    nobody else ever sees.
    """
    try:
        user, reset, token = create_panel_user(
            session, email=payload.email, role=payload.role
        )
    except EmailAlreadyUsed as error:
        raise HTTPException(status_code=409, detail="email_already_used") from error

    # The row the service just issued, not `user.password_resets[-1]`: that
    # relationship has no ordering, so on a second reset it can hand back the
    # one this call has just expired, reporting a dead expiry next to a live
    # token.
    return PasswordResetResponse(
        user=PanelUserResponse.model_validate(user),
        token=token,
        expires_at=reset.expires_at,
    )


@router.patch(
    "/{user_id}",
    response_model=PanelUserResponse,
    responses={
        403: {"description": "An administrator may not deactivate or demote themselves."},
        404: {"description": "No account with that id."},
    },
)
def update_user(
    user_id: int,
    payload: PanelUserUpdateRequest,
    admin: PanelUser = Depends(require_admin),
    session: Session = Depends(get_session),
) -> PanelUser:
    """Change a role, or switch an account off. Deactivation ends its sessions."""
    try:
        return update_panel_user(
            session,
            actor=admin,
            user_id=user_id,
            role=payload.role,
            is_active=payload.is_active,
        )
    except PanelUserNotFound as error:
        raise HTTPException(status_code=404, detail="panel_user_not_found") from error
    except SelfManagementRefused as error:
        raise HTTPException(status_code=403, detail="self_lockout_refused") from error


@router.post(
    "/{user_id}/password-resets",
    response_model=PasswordResetResponse,
    status_code=201,
    responses={404: {"description": "No account with that id."}},
)
def issue_reset(
    user_id: int,
    _admin: PanelUser = Depends(require_admin),
    session: Session = Depends(get_session),
) -> PasswordResetResponse:
    """Issue a one-time token so someone can set a new password.

    Any token issued earlier stops working. Sessions keep running until the
    token is actually spent, so issuing one by mistake does not throw anybody
    out mid-edit.
    """
    try:
        user, reset, token = reset_password_for(session, user_id)
    except PanelUserNotFound as error:
        raise HTTPException(status_code=404, detail="panel_user_not_found") from error

    return PasswordResetResponse(
        user=PanelUserResponse.model_validate(user),
        token=token,
        expires_at=reset.expires_at,
    )
