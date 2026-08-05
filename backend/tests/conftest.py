"""Shared fixtures.

Most tests must run without a database: they have to be fast, and an agent
needs feedback even when the stack is down. Tests that genuinely exercise
PostgreSQL are marked `integration` and skip themselves when it is unreachable.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import engine, get_session
from app.main import app


class StubSession:
    """Stands in for a SQLAlchemy session; records what was executed."""

    def __init__(self) -> None:
        self.executed: list[str] = []
        self.closed = False

    def execute(self, statement, *_args, **_kwargs):
        self.executed.append(str(statement))
        return None

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Client with the database dependency replaced by a stub."""
    stub = StubSession()
    app.dependency_overrides[get_session] = lambda: stub
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def raw_client() -> Iterator[TestClient]:
    """Client with no overrides, so the real dependency chain runs."""
    app.dependency_overrides.clear()
    yield TestClient(app)


@pytest.fixture(scope="session")
def database_available() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True


@pytest.fixture
def require_database(database_available: bool) -> None:
    if not database_available:
        pytest.skip("no reachable database; start the stack with docker compose up")
