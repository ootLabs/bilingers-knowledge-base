"""A database failure anywhere in the panel answers 503, not 500.

The distinction is not cosmetic. A 500 tells a client the request itself was
hopeless, when a dropped connection is exactly the case where retrying works,
and an unhandled exception on `/api/panel/sessions` puts a traceback where an
unauthenticated caller can read it.

Every panel service function a router or the session dependency calls is
checked, because a decorator that guards nine of ten entry points guarantees
nothing about the tenth. The HTTP end of it is checked separately: the
authenticated case fails inside `current_panel_session`, before any handler
body exists, which is why the translation lives in `app.main` rather than in
each router (see `app.services.panel_errors`).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db import get_session
from app.main import app
from app.models.panel import PanelRole, PanelSession, PanelUser
from app.security import hash_password
from app.services import rate_limit
from app.services.panel_auth import (
    login,
    record_throttled_attempt,
    resolve_session,
    revoke_session,
)
from app.services.panel_errors import PanelServiceUnavailable
from app.services.panel_passwords import change_password, set_password_with_token
from app.services.panel_users import (
    create_panel_user,
    list_panel_users,
    reset_password_for,
    update_panel_user,
)
from tests.conftest import auth_header

PASSWORD = "haslo-redaktorki-panelu"
NEW_PASSWORD = "nowe-haslo-redaktorki"


def _dropped() -> OperationalError:
    """What SQLAlchemy raises when the connection is gone mid-statement."""
    return OperationalError("SELECT 1", {}, Exception("server closed the connection"))


class DroppedConnection:
    """Session double whose every statement fails.

    Not `StubSession` from `conftest.py`: that one answers `execute` with
    `None` to stand in for a liveness probe, and the point here is the opposite
    - that nothing the panel asks of the database succeeds.
    """

    def execute(self, *_args: object, **_kwargs: object) -> object:
        raise _dropped()

    def get(self, *_args: object, **_kwargs: object) -> object:
        raise _dropped()

    def begin_nested(self) -> object:
        raise _dropped()

    def flush(self) -> None:
        raise _dropped()

    def commit(self) -> None:
        raise _dropped()

    def add(self, _instance: object) -> None:
        """Deliberately harmless: `add` alone touches no connection, so a
        failure has to come from the flush or commit that follows it."""

    def close(self) -> None:
        pass


def _entry_points() -> dict[str, Callable[[], object]]:
    """Every panel service function reachable from HTTP, with the smallest
    arguments that carry it as far as its first statement.

    Built fresh per call so no test can be influenced by another's leftovers,
    and keyed by name so a failure names the function that is not guarded.

    Nothing here hashes a password while the dictionary is being built: this
    runs at collection time to produce the parameter list, where the
    `cheap_password_hashing` fixture is not in effect yet and cost 12 would be
    paid for real.
    """
    session = DroppedConnection()
    user = PanelUser(
        id=1,
        email="magdalena@fundacja.test",
        password_hash=None,
        role=PanelRole.ADMIN,
    )
    panel_session = PanelSession(
        id=1,
        panel_user_id=1,
        token_hash="a" * 64,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    return {
        "login": lambda: login(session, email=user.email, password=PASSWORD),
        "resolve_session": lambda: resolve_session(session, "dowolny-token"),
        "revoke_session": lambda: revoke_session(session, panel_session),
        "record_throttled_attempt": lambda: record_throttled_attempt(
            session, email=user.email
        ),
        "set_password_with_token": lambda: set_password_with_token(
            session, token="dowolny-token", new_password=NEW_PASSWORD
        ),
        # The only one that needs a real hash: it verifies the current password
        # before it writes anything, and a `None` hash would end the call at
        # `AuthenticationFailed` without ever reaching the database.
        "change_password": lambda: change_password(
            session,
            user=PanelUser(
                id=1,
                email=user.email,
                password_hash=hash_password(PASSWORD),
                role=PanelRole.ADMIN,
            ),
            current_password=PASSWORD,
            new_password=NEW_PASSWORD,
        ),
        "create_panel_user": lambda: create_panel_user(
            session, email="justyna@fundacja.test", role=PanelRole.EDITOR
        ),
        "list_panel_users": lambda: list_panel_users(session),
        "update_panel_user": lambda: update_panel_user(
            session, actor=user, user_id=2, is_active=False
        ),
        "reset_password_for": lambda: reset_password_for(session, 2),
    }


@pytest.fixture
def broken_client() -> Iterator[TestClient]:
    """Client whose database session fails on every statement."""
    app.dependency_overrides[get_session] = lambda: DroppedConnection()
    # Process-global, same reason `panel_client` does it: without the reset a
    # previous test's attempts count against this one's throttle budget.
    rate_limit.reset()
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestServiceTranslation:
    @pytest.mark.parametrize("entry_point", sorted(_entry_points()))
    def test_a_dropped_connection_becomes_the_panel_domain_exception(
        self, entry_point: str, cheap_password_hashing: None
    ) -> None:
        """`SQLAlchemyError` must not cross the service boundary: the HTTP
        layer only translates exceptions it knows, and `docs/architecture.md`
        records that rule as binding on every DB-backed router."""
        with pytest.raises(PanelServiceUnavailable) as refused:
            _entry_points()[entry_point]()
        assert isinstance(refused.value.__cause__, OperationalError)


class TestHttpTranslation:
    def test_logging_in_answers_503(self, broken_client: TestClient) -> None:
        response = broken_client.post(
            "/api/panel/sessions",
            json={"email": "magdalena@fundacja.test", "password": PASSWORD},
        )
        assert response.status_code == 503
        assert response.json()["detail"] == "database_unavailable"

    def test_an_authenticated_request_answers_503_too(
        self, broken_client: TestClient
    ) -> None:
        """This one fails inside the session dependency, so no router body ever
        runs: it is the case an `except` in each handler could not catch."""
        response = broken_client.get(
            "/api/panel/users/me", headers=auth_header("dowolny-token")
        )
        assert response.status_code == 503
        assert response.json()["detail"] == "database_unavailable"

    def test_the_same_key_as_the_chat_endpoint_uses(
        self, broken_client: TestClient
    ) -> None:
        """One condition, one key for the frontend copy layer to translate."""
        response = broken_client.delete(
            "/api/panel/sessions/current", headers=auth_header("dowolny-token")
        )
        assert response.json()["detail"] == "database_unavailable"

    def test_a_missing_token_is_still_a_401_not_a_503(
        self, broken_client: TestClient
    ) -> None:
        """Credentials are checked before the database is touched, and an
        outage must not start answering unauthenticated callers differently."""
        response = broken_client.get("/api/panel/users/me")
        assert response.status_code == 401

    def test_the_openapi_schema_advertises_the_503(
        self, broken_client: TestClient
    ) -> None:
        """Declared on the router, so every panel endpoint carries it."""
        paths = broken_client.get("/openapi.json").json()["paths"]
        assert "503" in paths["/api/panel/sessions"]["post"]["responses"]
        assert "503" in paths["/api/panel/users"]["get"]["responses"]
