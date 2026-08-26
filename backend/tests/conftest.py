"""Shared fixtures.

Most tests must run without a database: they have to be fast, and an agent
needs feedback even when the stack is down. Tests that genuinely exercise
PostgreSQL are marked `integration` and skip themselves when it is unreachable.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import engine, get_session
from app.main import app


class StubSession:
    """Stands in for a SQLAlchemy session; records what was executed.

    `execute()` always returns `None` and there is no `add`/`commit`/`flush`:
    this only stands in for a *liveness*-style check (`SELECT 1` and similar,
    see `test_health.py`). A test that posts a valid, fully-processed request
    against the `client` fixture and expects the real service layer to run
    will hit an `AttributeError` here, not real coverage - use `raw_client`
    or `migrated_database` + `db_session`/`SessionLocal` against real
    PostgreSQL for anything past request validation.
    """

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


@pytest.fixture
def db_session(require_database: None) -> Iterator[Session]:
    """Session that always rolls back, so tests leave no rows behind.

    `autoflush=False, expire_on_commit=False` matches `app.db.SessionLocal`
    on purpose: a test running against SQLAlchemy's defaults instead would
    exercise different flush/expiry timing than real request traffic ever
    gets, and could pass while masking a bug that only shows up under
    `autoflush=False` (a read that depended on an implicit flush, say).
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, autoflush=False, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        # A failed flush leaves the transaction deassociated, so rolling back
        # unconditionally would warn about a transaction that is already gone.
        if connection.in_transaction():
            transaction.rollback()
        connection.close()


@pytest.fixture
def migrated_database(require_database: None) -> None:
    """Skip when the database is up but migrations have not been applied."""
    if not inspect(engine).has_table("alembic_version"):
        pytest.skip("database not migrated; run: docker compose exec backend alembic upgrade head")
