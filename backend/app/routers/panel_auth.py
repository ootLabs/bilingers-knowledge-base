"""HTTP layer for panel authentication: your own session and your own password.

Managing other people's accounts is `panel_users.py`. The split is by who the
endpoint is for, not by resource: everything here is something a logged-in
person (or someone holding a setup token) does to themselves, and needs no
role check beyond being authenticated.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.config import settings
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
    AuthenticationFailed,
    login,
    record_throttled_attempt,
    revoke_session,
)
from app.services.panel_passwords import (
    InvalidPasswordResetToken,
    change_password,
    set_password_with_token,
)
from app.services.rate_limit import TooManyAttempts
from app.services.rate_limit import check as check_ip_rate_limit

router = APIRouter(prefix="/api/panel", tags=["panel"])


def _client_ip(request: Request) -> str | None:
    """The caller's address, as far as the server can honestly tell.

    `X-Forwarded-For` is deliberately not read: nothing in front of this
    service sets it today, so trusting it would let any client write whatever
    it likes into the audit trail. Revisit when a real proxy is in front.

    That is now a condition of deployment, not just a note about audit
    quality: since the per-IP throttle keys on this value, anything
    terminating TLS ahead of the service (nginx, Traefik, a cloud load
    balancer) would make every caller share one address and one budget, and
    20 wrong passwords from one attacker would shut the whole foundation out
    of the panel for the window. Putting a proxy in front means teaching this
    function to read a forwarded header from it first, and to trust that
    header from the proxy alone.
    """
    return request.client.host if request.client else None


@router.post(
    "/sessions",
    response_model=PanelSessionResponse,
    status_code=201,
    responses={
        401: {"description": "Wrong credentials, or the account cannot log in."},
        429: {"description": "Too many attempts from this address."},
    },
)
def open_session(
    payload: PanelLoginRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> PanelSessionResponse:
    """Log in. The response carries the session token exactly once.

    A locked, deactivated or nonexistent account all answer with the same
    401: a distinct status for a locked account would tell an anonymous
    caller which addresses have one, and answering faster than a wrong
    password would tell them the same thing by timing alone.

    Checked before any of that: how many attempts this address has made
    recently. `login` pays for a bcrypt comparison on every call, including
    for an unknown account, precisely so it cannot be used to fingerprint
    addresses; the IP throttle is what stops that cost being spent on a flood.
    A throttled attempt still leaves one audit row per address per window, so
    a flood is visible in `panel_login_attempts` rather than silent.
    """
    ip = _client_ip(request)
    if ip is not None:
        try:
            check_ip_rate_limit(
                ip,
                max_attempts=settings.panel_login_ip_max_attempts,
                window_minutes=settings.panel_login_ip_window_minutes,
            )
        except TooManyAttempts as error:
            if error.first_in_window:
                # One row per address per window, not one per refused request:
                # the audit table has to show that a flood happened without
                # becoming the thing the flood fills up (retention is still
                # open, B-07).
                record_throttled_attempt(
                    session,
                    email=payload.email,
                    ip_address=ip,
                    user_agent=request.headers.get("user-agent") or None,
                )
            raise HTTPException(
                status_code=429,
                detail="too_many_requests",
                headers={"Retry-After": str(error.retry_after_seconds)},
            ) from error

    try:
        panel_session, token = login(
            session,
            email=payload.email,
            password=payload.password,
            ip_address=ip,
            user_agent=request.headers.get("user-agent") or None,
        )
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
