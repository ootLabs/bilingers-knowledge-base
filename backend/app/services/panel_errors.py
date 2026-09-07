"""One domain exception for a database failure anywhere in the panel.

Here rather than in `panel_auth` because all three panel services raise it and
none of them owns it, the same reason `dependencies.py` sits outside `routers/`.

`docs/conventions.md` says a service raises a domain exception and the HTTP
layer translates it, and `docs/architecture.md` records `app.services.chat`
setting that precedent for every DB-backed router. The panel needs the same
guarantee for a different reason than chat did: a dropped connection during a
login must answer 503, not 500, because a 500 tells a client to give up on a
request that retrying would satisfy, and it puts a stack trace where an
unauthenticated caller can read it.

Unlike chat, there is no client-fault branch here. Chat discovers bad input at
the driver (a NUL byte in a question) and has to tell that apart from an
outage, whereas every panel string the database ever sees is either
server-minted or has been through a Pydantic schema first (see
`app.schemas.panel`). So one exception and one status is the whole rule; the
day the panel gains an input the boundary genuinely cannot judge, split it then
rather than carrying an unused branch until it rots.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from sqlalchemy.exc import SQLAlchemyError

_P = ParamSpec("_P")
_R = TypeVar("_R")


class PanelServiceUnavailable(Exception):
    """The panel could not reach the database. Nobody's fault, maps to a 503."""


def unavailable_on_database_failure(function: Callable[_P, _R]) -> Callable[_P, _R]:
    """Turn any driver failure raised inside `function` into the exception above.

    A decorator rather than chat's explicit `try`/`except` blocks, because the
    rule it applies is uniform: every panel service function is reached by one
    HTTP request that either works or fails whole, so there is no per-call-site
    judgement to make, and ten copies of the same three lines would be ten
    places for the next one to be forgotten.

    Applied to the functions a router or a dependency calls, not to the helpers
    underneath them: the boundary that matters is the one a service is entered
    through. Nesting is harmless anyway, since `PanelServiceUnavailable` is not
    a `SQLAlchemyError` and passes back out through an outer decorator untouched.

    Nothing is rolled back here on purpose. `get_session` closes the session
    when the request ends, which rolls back whatever the failed statement left
    open, and a rollback attempt on a connection that has just dropped raises a
    second exception that buries the first.
    """

    @wraps(function)
    def guarded(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        try:
            return function(*args, **kwargs)
        except SQLAlchemyError as error:
            raise PanelServiceUnavailable(function.__qualname__) from error

    return guarded
