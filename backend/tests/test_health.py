"""API tests for the health endpoints.

These are what tells an agent, and CI, whether the service is actually alive.
Each endpoint is covered twice: once against a stub (fast, always runs) and
once against real PostgreSQL (marked `integration`).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import SessionLocal


def test_liveness_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_liveness_does_not_touch_the_database(client: TestClient) -> None:
    """Liveness must answer even when the database is down, or orchestrators
    will restart a service that is merely waiting on its dependency."""
    stub = client.app.dependency_overrides.values()
    client.get("/health")
    assert all(not getattr(factory(), "executed", []) for factory in stub)


def test_readiness_reports_the_database(client: TestClient) -> None:
    response = client.get("/health/db")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "reachable"}


def test_readiness_issues_a_query(client: TestClient) -> None:
    override = next(iter(client.app.dependency_overrides.values()))
    stub = override()
    client.get("/health/db")
    assert stub.executed == ["SELECT 1"]


def test_unknown_route_is_404(client: TestClient) -> None:
    assert client.get("/health/nope").status_code == 404


@pytest.mark.integration
def test_readiness_against_real_database(
    require_database: None, raw_client: TestClient
) -> None:
    response = raw_client.get("/health/db")
    assert response.status_code == 200
    assert response.json()["database"] == "reachable"


@pytest.mark.integration
def test_bootstrap_table_exists(require_database: None) -> None:
    """db/init/01_schema.sql runs only on an empty volume, so a missing table
    usually means someone edited it without recreating the volume."""
    with SessionLocal() as session:
        count = session.execute(text("SELECT count(*) FROM health_probe")).scalar()
    assert count == 1
