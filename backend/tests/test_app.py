"""Tests for app assembly: routing, CORS, and the session dependency."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import settings
from app.main import app


def test_root_points_at_the_docs(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"service": settings.app_name, "docs": "/docs"}


def test_openapi_schema_is_served(client: TestClient) -> None:
    """A broken schema breaks /docs, which is how a human explores this API."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "/health" in response.json()["paths"]


def test_allowed_origin_gets_cors_headers(client: TestClient) -> None:
    origin = settings.cors_origin_list[0]
    response = client.get("/health", headers={"Origin": origin})
    assert response.headers["access-control-allow-origin"] == origin


def test_disallowed_origin_gets_no_cors_headers(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "https://not-allowed.test"})
    assert "access-control-allow-origin" not in response.headers


def test_preflight_is_answered(client: TestClient) -> None:
    response = client.options(
        "/health",
        headers={
            "Origin": settings.cors_origin_list[0],
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200


def test_routers_are_wired_once() -> None:
    """A router included twice silently shadows routes and is easy to miss.

    Compared per method, not per path: one path legitimately answers several
    verbs (`/api/panel/users` lists and creates), and comparing paths alone
    would report that as a duplicate while still missing a router included
    twice with different methods.
    """
    endpoints = [(route.path, method) for route in app.routes for method in route.methods]
    assert len(endpoints) == len(set(endpoints))


def test_get_session_yields_and_always_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    """A session left open leaks a pooled connection; under load that exhausts
    the pool and the whole service stops answering."""
    closed: list[bool] = []

    class FakeSession:
        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(db, "SessionLocal", lambda: FakeSession())

    generator = db.get_session()
    session: Any = next(generator)
    assert isinstance(session, FakeSession)

    with pytest.raises(StopIteration):
        next(generator)
    assert closed == [True]


def test_get_session_closes_even_when_the_caller_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[bool] = []

    class FakeSession:
        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(db, "SessionLocal", lambda: FakeSession())

    generator = db.get_session()
    next(generator)
    generator.close()
    assert closed == [True]
