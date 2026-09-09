"""HTTP layer for the panel's second factor (T-83).

Split by who the endpoint is for, the same rule as `panel_auth.py` against
`panel_users.py`: everything under `/users/me` is somebody acting on their own
account, and the one route under `/users/{id}` is an administrator clearing
somebody else's, which is the recovery path for a lost phone.

Every action here lands in the change journal, because switching a second factor
on or off is exactly the kind of thing an incident needs a timeline for (T-89).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db import get_session
from app.dependencies import current_panel_user, require_admin
from app.models.audit import AuditAction
from app.models.panel import PanelUser
from app.schemas.panel_two_factor import (
    BackupCodesResponse,
    TwoFactorCodeRequest,
    TwoFactorEnrolmentResponse,
    TwoFactorStatusResponse,
)
from app.services.panel_audit import record_event
from app.services.panel_two_factor import (
    InvalidSecondFactor,
    TwoFactorAlreadyOn,
    TwoFactorNotEnrolled,
    begin_enrolment,
    confirm_enrolment,
    disable_for_self,
    has_second_factor,
    reset_for,
    unused_backup_code_count,
)
from app.services.panel_users import PanelUserNotFound, get_panel_user

router = APIRouter(
    prefix="/api/panel",
    tags=["panel"],
    responses={
        401: {"description": "No usable session token."},
        503: {"description": "The database or the encryption key is unavailable."},
    },
)

_NOT_ENROLLED = {409: {"description": "Nothing is enrolled for this account."}}
# A wrong code is a 422, not a 401, and that is not pedantry: the request is
# perfectly authenticated, it is the six digits that are wrong. A 401 here would
# tell the frontend's session handling that the token had stopped working, and
# it would sign the editor out for mistyping a code.
_BAD_CODE = {422: {"description": "The code does not match."}}

# `TwoFactorNotConfigured` is deliberately not caught in this file. It becomes a
# 503 carrying `X-Second-Factor: not-configured` in the app-level handler in
# `app.main`, which is also what answers it on the login endpoint: the same
# condition reached from five routes, translated once.


@router.get("/users/me/two-factor", response_model=TwoFactorStatusResponse)
def read_status(
    user: PanelUser = Depends(current_panel_user),
    session: Session = Depends(get_session),
) -> TwoFactorStatusResponse:
    """Whether this account has a second factor, and how much paper is left."""
    return TwoFactorStatusResponse(
        enabled=has_second_factor(session, user),
        unused_backup_codes=unused_backup_code_count(session, user),
    )


@router.post(
    "/users/me/two-factor",
    response_model=TwoFactorEnrolmentResponse,
    status_code=201,
    responses={409: {"description": "This account already has a second factor."}},
)
def start_enrolment(
    user: PanelUser = Depends(current_panel_user),
    session: Session = Depends(get_session),
) -> TwoFactorEnrolmentResponse:
    """Mint a secret and hand it over once. Nothing is switched on yet.

    Two steps, because a secret that gated logins the moment it was created
    would lock out anybody whose authenticator did not end up holding it.
    """
    try:
        enrolment = begin_enrolment(session, user)
    except TwoFactorAlreadyOn as error:
        raise HTTPException(status_code=409, detail="two_factor_already_on") from error
    return TwoFactorEnrolmentResponse(
        secret=enrolment.secret, otpauth_uri=enrolment.otpauth_uri
    )


@router.post(
    "/users/me/two-factor/confirm",
    response_model=BackupCodesResponse,
    responses=_NOT_ENROLLED | _BAD_CODE,
)
def confirm(
    payload: TwoFactorCodeRequest,
    user: PanelUser = Depends(current_panel_user),
    session: Session = Depends(get_session),
) -> BackupCodesResponse:
    """Prove the authenticator works, switch 2FA on, and print the codes.

    The backup codes are in this response and nowhere else, ever: only their
    hashes are kept, the same rule as a session token.
    """
    try:
        codes = confirm_enrolment(session, user, payload.code)
    except TwoFactorNotEnrolled as error:
        raise HTTPException(status_code=409, detail="two_factor_not_enrolled") from error
    except TwoFactorAlreadyOn as error:
        raise HTTPException(status_code=409, detail="two_factor_already_on") from error
    except InvalidSecondFactor as error:
        raise HTTPException(status_code=422, detail="invalid_code") from error

    record_event(session, actor=user, action=AuditAction.TWO_FACTOR_ENABLED)
    return BackupCodesResponse(codes=codes)


@router.post("/users/me/two-factor/disable", status_code=204, responses=_NOT_ENROLLED | _BAD_CODE)
def disable(
    payload: TwoFactorCodeRequest,
    user: PanelUser = Depends(current_panel_user),
    session: Session = Depends(get_session),
) -> Response:
    """Switch your own second factor off, proving you can still pass it.

    `POST .../disable` rather than `DELETE .../two-factor`, because this needs a
    body: a DELETE that carries one is awkward for clients and proxies alike,
    and requiring the code is the point. A stolen session must not be able to
    quietly remove the thing that makes it useless.
    """
    try:
        disable_for_self(session, user, payload.code)
    except TwoFactorNotEnrolled as error:
        raise HTTPException(status_code=409, detail="two_factor_not_enrolled") from error
    except InvalidSecondFactor as error:
        raise HTTPException(status_code=422, detail="invalid_code") from error

    record_event(session, actor=user, action=AuditAction.TWO_FACTOR_DISABLED)
    return Response(status_code=204)


@router.post(
    "/users/{user_id}/two-factor-resets",
    status_code=204,
    responses=_NOT_ENROLLED | {404: {"description": "No account with that id."}},
)
def reset_for_account(
    user_id: int,
    admin: PanelUser = Depends(require_admin),
    session: Session = Depends(get_session),
) -> Response:
    """An administrator clears somebody's second factor. The recovery path.

    A lost phone with the printed codes in the same bag is what this exists for.
    Deliberately an administrator's action and not self-service: a "reset my
    2FA" link that anybody holding the password could use would not be a second
    factor at all. Who did it and to whom is in the journal.
    """
    try:
        target = get_panel_user(session, user_id)
        reset_for(session, target)
    except PanelUserNotFound as error:
        raise HTTPException(status_code=404, detail="panel_user_not_found") from error
    except TwoFactorNotEnrolled as error:
        raise HTTPException(status_code=409, detail="two_factor_not_enrolled") from error

    record_event(
        session,
        actor=admin,
        action=AuditAction.TWO_FACTOR_RESET,
        subject_type="panel_user",
        subject_id=user_id,
    )
    return Response(status_code=204)
