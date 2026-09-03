from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import chat, health, panel_auth, panel_users
from app.services.panel_errors import PanelServiceUnavailable

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(health.router)
app.include_router(panel_auth.router)
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


@app.get("/")
def root() -> dict[str, str]:
    return {"service": settings.app_name, "docs": "/docs"}
