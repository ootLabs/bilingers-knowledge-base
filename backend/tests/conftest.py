"""Shared fixtures.

Most tests must run without a database: they have to be fast, and an agent
needs feedback even when the stack is down. Tests that genuinely exercise
PostgreSQL are marked `integration` and skip themselves when it is unreachable.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import security
from app.db import engine, get_session
from app.main import app
from app.models import Base
from app.models.panel import PanelRole, PanelUser
from app.services import rate_limit

# Long enough for the panel's own rule (12 characters), and obviously fake.
ADMIN_PASSWORD = "administrator-haslo"
EDITOR_PASSWORD = "redaktorka-haslo"


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
def panel_db() -> Iterator[Session]:
    """The mapped schema in an in-memory SQLite database, one per test.

    Authentication cannot be tested against `StubSession`: every rule in it is
    a query or a write, and a stub would only prove the router calls something.
    It also cannot be *only* tested against PostgreSQL, because then the whole
    panel would sit behind `integration` and vanish from a run with nothing
    started, which is the run an agent does after every edit.

    So the behaviour runs here, on real SQL against the same models, and the
    guarantees that are specifically PostgreSQL's (the migration chain, the
    unique constraint, how the role enum is stored) are asserted against
    PostgreSQL in the `integration` classes. Anything that depends on a
    server-side type or on a database-enforced constraint belongs there, not
    here.

    `StaticPool` keeps every connection pointed at the same in-memory database;
    without it each connection would get its own empty one.
    """
    sqlite_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(sqlite_engine)
    # Matches `app.db.SessionLocal` rather than SQLAlchemy defaults, so the
    # tests exercise the same flush and expiry timing as real request traffic.
    session = Session(bind=sqlite_engine, autoflush=False, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        sqlite_engine.dispose()


@pytest.fixture
def panel_client(panel_db: Session) -> Iterator[TestClient]:
    """Client backed by `panel_db`, reaching the real routers and services."""
    app.dependency_overrides[get_session] = lambda: panel_db
    # The IP rate limiter is process-global (see `app.services.rate_limit`),
    # not per-test like `panel_db`: without this, attempts from one test's
    # client would count against the next one's, all sharing the same
    # synthetic TestClient address.
    rate_limit.reset()
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def postgres_panel_client(
    migrated_database: None, db_session: Session
) -> Iterator[TestClient]:
    """The same client against real PostgreSQL, inside a rolled-back transaction.

    For the handful of tests that have to prove the panel works on the database
    it actually runs on: the migrated schema, the real driver, real constraints.
    """
    app.dependency_overrides[get_session] = lambda: db_session
    rate_limit.reset()
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def cheap_password_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hash at the lowest cost bcrypt allows, for the duration of one test.

    Production hashes at cost 12, which is roughly a quarter of a second per
    attempt on purpose. These tests care about which answer comes back, not how
    long it took, and a suite that pays the real cost on every login stops being
    something an agent runs after every edit.
    """
    monkeypatch.setattr(security, "_BCRYPT_ROUNDS", 4)


def make_panel_user(
    session: Session,
    *,
    email: str,
    password: str | None,
    role: PanelRole = PanelRole.EDITOR,
    is_active: bool = True,
) -> PanelUser:
    """Insert a panel account directly, bypassing the API that creates them.

    `password=None` produces the state an administrator leaves behind: a real
    account that cannot log in until its owner sets a password.
    """
    user = PanelUser(
        email=email,
        password_hash=security.hash_password(password) if password is not None else None,
        role=role,
        is_active=is_active,
    )
    session.add(user)
    session.flush()
    return user


@pytest.fixture
def panel_admin(cheap_password_hashing: None, panel_db: Session) -> PanelUser:
    return make_panel_user(
        panel_db,
        email="admin@fundacja.test",
        password=ADMIN_PASSWORD,
        role=PanelRole.ADMIN,
    )


@pytest.fixture
def panel_editor(cheap_password_hashing: None, panel_db: Session) -> PanelUser:
    return make_panel_user(
        panel_db,
        email="redaktorka@fundacja.test",
        password=EDITOR_PASSWORD,
        role=PanelRole.EDITOR,
    )


def log_in(client: TestClient, email: str, password: str) -> str:
    """Log in through the API and return the session token."""
    response = client.post("/api/panel/sessions", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return response.json()["token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
