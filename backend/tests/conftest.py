"""Shared fixtures.

Most tests must run without a database: they have to be fast, and an agent
needs feedback even when the stack is down. Tests that genuinely exercise
PostgreSQL are marked `integration` and skip themselves when it is unreachable.
"""

import uuid
from collections.abc import Callable, Iterator
from dataclasses import replace
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import SessionLocal, engine, get_session
from app.main import app
from app.models.chat import ChatSession, Query
from app.services.usage import PricedUsage


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


@pytest.fixture
def committed_token() -> Iterator[Callable[[], str]]:
    """Mints `chat_sessions.token` values for tests that commit for real,
    through the live endpoint or a real session, and deletes their rows after.

    `uuid4().hex` is 32 lowercase hex characters, exactly what `ChatRequest`
    requires and what a real client is expected to mint, and it will not
    collide with a previous run.

    Deleting `chat_sessions` cascades to `queries` (`ondelete="CASCADE"`), so
    this also removes their questions - `queries.question` is marked
    PERSONAL_DATA, and a local `pytest` run targets a developer's actual
    database, so leftover rows are not just clutter.
    """
    tokens: list[str] = []

    def make() -> str:
        token = uuid.uuid4().hex
        tokens.append(token)
        return token

    yield make

    if tokens:
        with SessionLocal() as session:
            session.execute(delete(ChatSession).where(ChatSession.token.in_(tokens)))
            session.commit()


@pytest.fixture
def committed_query(committed_token: Callable[[], str]) -> Callable[[], int]:
    """A chat session and its question, committed, exactly as `/chat` leaves
    them: a row in the ledger with no measurement on it yet.

    Returns the query id rather than the instance, because the cost writer takes
    an id: the row it completes is normally loaded on a session of its own.
    Cleanup comes from `committed_token`, which cascades to `queries`.
    """

    def make() -> int:
        with SessionLocal() as session:
            chat_session = ChatSession(token=committed_token())
            session.add(chat_session)
            session.flush()
            query = Query(chat_session_id=chat_session.id, question="Pytanie o dwujezycznosc")
            session.add(query)
            session.commit()
            return query.id

    return make


# Fixed numbers rather than generated ones: they are asserted on directly in
# every module that measures anything, and 1000 input plus 200 output tokens at
# the price list in `test_usage.py` works out to exactly 0.000270 USD.
BASELINE_USAGE = PricedUsage(
    model="small",
    input_tokens=1000,
    output_tokens=200,
    duration_ms=900,
    cost_usd=Decimal("0.000270"),
    cost_pln=Decimal("0.001080"),
    fx_rate_pln_per_usd=Decimal("4.000000"),
    pricing_version="test-2026-08",
)


@pytest.fixture
def priced_usage() -> Callable[..., PricedUsage]:
    """A ready measurement, with any field overridable by keyword.

    Needs no database, so tests that have none still use this rather than
    retyping the eight fields: one definition means one module cannot assert a
    cost that another one says is wrong.
    """

    def make(**overrides: object) -> PricedUsage:
        return replace(BASELINE_USAGE, **overrides)

    return make
