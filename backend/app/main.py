from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import (
    chat,
    health,
    panel_audit,
    panel_auth,
    panel_document_imports,
    panel_documents,
    panel_publishing,
    panel_two_factor,
    panel_users,
)
from app.services.panel_errors import PanelServiceUnavailable
from app.services.panel_totp import TwoFactorNotConfigured

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # A browser hides every response header from a cross-origin script unless
    # it is listed here. The login form needs this one to know it should ask for
    # a second factor (T-83), and it is a header rather than a field in the
    # body because the frontend never reads a failed response's body.
    expose_headers=["X-Second-Factor"],
)

app.include_router(chat.router)
app.include_router(health.router)
app.include_router(panel_auth.router)
app.include_router(panel_documents.router)
app.include_router(panel_document_imports.router)
app.include_router(panel_publishing.router)
app.include_router(panel_audit.router)
app.include_router(panel_two_factor.router)
app.include_router(panel_users.router)


@app.exception_handler(PanelServiceUnavailable)
def panel_service_unavailable(
    _request: Request, _error: PanelServiceUnavailable
) -> JSONResponse:
    """A database failure in the panel is a 503, wherever it was raised.

    Registered once here rather than translated in each handler, and that is
    not only about repeating nine identical `except` blocks: `resolve_session`
    runs inside the `current_panel_session` dependency, so on every
    authenticated request it fails *before* any handler body exists to catch
    it. An app-level handler is the only place that covers both.

    `detail` is the same key `/chat` returns for the same condition, because
    one condition should not have two names for the frontend copy layer to
    learn (`docs/conventions.md`). No logging call here: the project has no
    logging setup of its own yet (only uvicorn's, which records the 503), and
    handling the exception is what stops the traceback reaching the container
    log - so when logging is wired up, this is one of the places that has to
    say what it swallowed.
    """
    return JSONResponse(status_code=503, content={"detail": "database_unavailable"})


@app.exception_handler(TwoFactorNotConfigured)
def two_factor_not_configured(
    _request: Request, _error: TwoFactorNotConfigured
) -> JSONResponse:
    """No usable TOTP encryption key, wherever the panel noticed.

    503 rather than 500: the deployment is missing a key, which is an
    operator's problem and not the caller's, and it is fixable without a code
    change. The header is what tells this 503 apart from a database outage for
    a frontend that never reads a failed response's body, and it is the header
    already listed in `expose_headers` above.

    Registered here rather than translated per router, and that is the whole
    point of moving it: the same exception reaches `/api/panel/sessions` (an
    enrolled account logging in after the key was rotated) and four routes
    under `/users/me/two-factor`, and translating it five times is four places
    to get it right and one to forget the header in. Login was that one.
    """
    return JSONResponse(
        status_code=503,
        content={"detail": "two_factor_not_configured"},
        headers={"X-Second-Factor": "not-configured"},
    )


@app.get("/")
def root() -> dict[str, str]:
    return {"service": settings.app_name, "docs": "/docs"}
