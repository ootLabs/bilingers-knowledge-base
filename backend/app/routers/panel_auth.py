"""HTTP layer for panel authentication: your own session and your own password.

Managing other people's accounts is `panel_users.py`. The split is by who the
endpoint is for, not by resource: everything here is something a logged-in
person (or someone holding a setup token) does to themselves, and needs no
role check beyond being authenticated.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.db import get_session
from app.dependencies import current_panel_session
from app.models.panel import PanelSession, PanelUser
from app.schemas.panel import (
    PanelLoginRequest,
    PanelSessionResponse,
    PanelUserResponse,
    PasswordChangeRequest,
    PasswordResetConfirmRequest,
)
from app.services.panel_auth import (
    AccountLocked,
    AuthenticationFailed,
    login,
    revoke_session,
    utcnow,
)
from app.services.panel_passwords import (
    InvalidPasswordResetToken,
    change_password,
    set_password_with_token,
)

router = APIRouter(prefix="/api/panel", tags=["panel"])

# Truncated to what the column holds. A user agent longer than this is either a
# bloated real one or someone probing, and neither is worth a 500.
_USER_AGENT_LIMIT = 255


def _client_ip(request: Request) -> str | None:
    """The caller's address, as far as the server can honestly tell.

    `X-Forwarded-For` is deliberately not read: nothing in front of this
    service sets it today, so trusting it would let any client write whatever
    it likes into the audit trail. Revisit when a real proxy is in front.
    """
    return request.client.host if request.client else None


@router.post(
    "/sessions",
    response_model=PanelSessionResponse,
    status_code=201,
    responses={
        401: {"description": "Wrong credentials, or the account cannot log in."},
        423: {"description": "Too many failed attempts; the account is locked."},
    },
)
def open_session(
    payload: PanelLoginRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> PanelSessionResponse:
    """Log in. The response carries the session token exactly once.

    A locked account gets 423 rather than the generic 401: with a handful of
    named accounts there is nothing to hide, and an editor who cannot get in
    needs to know whether to wait or to call the administrator.
    """
    try:
        panel_session, token = login(
            session,
            email=payload.email,
            password=payload.password,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent", "")[:_USER_AGENT_LIMIT] or None,
        )
    except AccountLocked as error:
        # Seconds to wait, per RFC 9110, not the moment the lock lifts: a
        # timestamp here reads as a delay of decades to anything that honours
        # the header, and the client would back off effectively forever.
        retry_after = max(1, int((error.locked_until - utcnow()).total_seconds()))
        raise HTTPException(
            status_code=423,
            detail="account_locked",
            headers={"Retry-After": str(retry_after)},
        ) from error
    except AuthenticationFailed as error:
        raise HTTPException(status_code=401, detail="invalid_credentials") from error

    return PanelSessionResponse(
        token=token,
        expires_at=panel_session.expires_at,
        user=PanelUserResponse.model_validate(panel_session.panel_user),
    )


@router.delete("/sessions/current", status_code=204)
def close_session(
    resolved: tuple[PanelUser, PanelSession] = Depends(current_panel_session),
    session: Session = Depends(get_session),
) -> Response:
    """Log out. Revokes this session only, not the account's other ones."""
    revoke_session(session, resolved[1])
    return Response(status_code=204)


@router.get("/users/me", response_model=PanelUserResponse)
def read_me(
    resolved: tuple[PanelUser, PanelSession] = Depends(current_panel_session),
) -> PanelUser:
    """Who this token belongs to. The panel reads the role from here."""
    return resolved[0]


@router.post("/users/me/password", status_code=204)
def change_own_password(
    payload: PasswordChangeRequest,
    resolved: tuple[PanelUser, PanelSession] = Depends(current_panel_session),
    session: Session = Depends(get_session),
) -> Response:
    """Change your own password. Other sessions end, this one survives."""
    user, panel_session = resolved
    try:
        change_password(
            session,
            user=user,
            current_password=payload.current_password,
            new_password=payload.new_password,
            keep_session_id=panel_session.id,
        )
    except AuthenticationFailed as error:
        raise HTTPException(status_code=401, detail="invalid_credentials") from error
    return Response(status_code=204)


@router.post("/password-resets/confirm", status_code=204)
def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    session: Session = Depends(get_session),
) -> Response:
    """Set a password using a token issued by an administrator.

    Unauthenticated by design: this is how an account gets its first password,
    and how someone who has forgotten theirs gets back in. The token is the
    credential, it is single use, and spending it ends every session the
    account had.
    """
    try:
        set_password_with_token(session, token=payload.token, new_password=payload.new_password)
    except InvalidPasswordResetToken as error:
        raise HTTPException(status_code=400, detail="invalid_reset_token") from error
    return Response(status_code=204)
