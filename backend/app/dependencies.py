"""FastAPI dependencies that turn a bearer token into an account.

Sits next to `config.py` and `db.py` rather than in `routers/`, because every
panel router needs it and none of them owns it. The rule from
`docs/conventions.md` still holds: the logic lives in `app.services.panel_auth`,
this module only adapts it to HTTP.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.panel import PanelRole, PanelSession, PanelUser
from app.services.panel_auth import resolve_session

# auto_error=False so a missing header produces the same 401 with the same body
# as a bad one. FastAPI's own error for a missing header is a 403, which would
# tell an unauthenticated caller that the token they did not send was the
# problem, and would need translating in every handler anyway.
bearer_scheme = HTTPBearer(auto_error=False, description="Panel session token")


def _unauthenticated() -> HTTPException:
    # `detail` is a key, not a sentence: the Polish copy lives in the frontend
    # (see `docs/conventions.md`). WWW-Authenticate is what makes this a
    # standards-compliant 401 rather than a 401-shaped body.
    return HTTPException(
        status_code=401,
        detail="not_authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def current_panel_session(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> tuple[PanelUser, PanelSession]:
    """The account and session behind this request, or a 401.

    Every reason to refuse (no header, unknown token, revoked, expired,
    deactivated account) is one answer. Which of them it was is the server's
    business, and telling a caller apart from the others is free reconnaissance.
    """
    if credentials is None or not credentials.credentials:
        raise _unauthenticated()

    resolved = resolve_session(session, credentials.credentials)
    if resolved is None:
        raise _unauthenticated()

    # Stashed for handlers that need the session row itself (logout) without
    # having to resolve the token a second time.
    request.state.panel_session = resolved[1]
    return resolved


def current_panel_user(
    resolved: tuple[PanelUser, PanelSession] = Depends(current_panel_session),
) -> PanelUser:
    return resolved[0]


def require_admin(user: PanelUser = Depends(current_panel_user)) -> PanelUser:
    """Guard for account management. Editors get a 403, not a 404.

    Hiding the endpoints from editors would be pointless here: they are in the
    OpenAPI schema, and every account in this panel is a colleague, not an
    anonymous visitor.
    """
    if user.role is not PanelRole.ADMIN:
        raise HTTPException(status_code=403, detail="admin_required")
    return user
