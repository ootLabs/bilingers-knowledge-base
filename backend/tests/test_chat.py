"""Tests for the `/chat` endpoint: request validation, error handling, the
no-orphan write order, and (against real PostgreSQL) actual persistence.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.chat import ChatSession, Query
from app.routers import chat as chat_router
from app.schemas.chat import ChatRequest
from app.services import chat as chat_service
from app.services.chat import (
    ChatServiceUnavailable,
    PLACEHOLDER_ANSWER,
    get_or_create_chat_session,
    record_query,
    stream_placeholder_answer,
)


def _unique_token(prefix: str) -> str:
    """A `chat_sessions.token` guaranteed not to collide with a previous run.

    Integration tests below go through the real endpoint, which commits for
    real; a literal token would accumulate rows every time the suite runs
    against a persistent database.
    """
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class TestValidation:
    """These never reach the service layer: Pydantic rejects the body first."""

    def test_blank_question_is_rejected(self, client: TestClient) -> None:
        response = client.post("/chat", json={"question": "   ", "session_token": "t"})
        assert response.status_code == 422

    def test_missing_session_token_is_rejected(self, client: TestClient) -> None:
        response = client.post("/chat", json={"question": "Pytanie"})
        assert response.status_code == 422

    def test_oversized_question_is_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/chat", json={"question": "a" * 4001, "session_token": "t"}
        )
        assert response.status_code == 422

    # A valid payload against the stubbed database is covered under
    # TestWiringAndErrors, which mocks the service layer instead of hitting
    # StubSession's minimal, execute()-returns-None interface. Whether it
    # really works against PostgreSQL is TestChatEndpointAgainstRealDatabase.

    def test_a_question_padded_past_the_limit_is_accepted_after_stripping(self) -> None:
        """max_length is enforced after stripping, not before: a question
        that only *looks* oversized because of stray surrounding whitespace
        must not be rejected for content that fits well under the limit."""
        request = ChatRequest(question=" " + "a" * 3999 + " ", session_token="t")
        assert request.question == "a" * 3999

    def test_an_all_whitespace_question_is_still_rejected(self) -> None:
        with pytest.raises(ValueError, match="question"):
            ChatRequest(question="   ", session_token="t")


class TestPlaceholderStream:
    """Pure function, no database: this is the stand-in for T-30/T-40."""

    def test_yields_more_than_one_chunk(self) -> None:
        chunks = list(stream_placeholder_answer("dowolne pytanie"))
        assert len(chunks) > 1

    def test_chunks_reconstruct_the_full_text(self) -> None:
        """No content lost or duplicated across a chunk boundary."""
        chunks = list(stream_placeholder_answer("dowolne pytanie"))
        assert "".join(chunks).strip() == PLACEHOLDER_ANSWER


class TestWiringAndErrors:
    """Fast, no database: verified by monkeypatching the service functions
    the router calls, the same way `test_app.py` verifies `get_session`."""

    def test_the_question_is_recorded_before_the_stream_starts(
        self, monkeypatch: pytest.MonkeyPatch, client: TestClient
    ) -> None:
        """The row that protects against orphaned mid-stream disconnects only
        protects anything if it lands before the response starts streaming."""
        call_order: list[str] = []

        def fake_get_or_create(_session: object, _token: str) -> ChatSession:
            call_order.append("session")
            return ChatSession(id=1, token="t")

        def fake_record_query(
            _session: object, _chat_session: ChatSession, _question: str
        ) -> Query:
            call_order.append("query")
            return Query(id=1, chat_session_id=1, question=_question)

        def fake_stream(_question: str):
            call_order.append("stream")
            yield "chunk"

        monkeypatch.setattr(chat_router, "get_or_create_chat_session", fake_get_or_create)
        monkeypatch.setattr(chat_router, "record_query", fake_record_query)
        monkeypatch.setattr(chat_router, "stream_placeholder_answer", fake_stream)

        response = client.post(
            "/chat", json={"question": "Pytanie", "session_token": "token"}
        )
        assert response.status_code == 200
        assert call_order == ["session", "query", "stream"]

    def test_a_database_error_becomes_a_503_not_a_broken_stream(
        self, monkeypatch: pytest.MonkeyPatch, client: TestClient
    ) -> None:
        def raise_error(_session: object, _token: str) -> ChatSession:
            raise ChatServiceUnavailable("database unavailable")

        monkeypatch.setattr(chat_router, "get_or_create_chat_session", raise_error)

        response = client.post(
            "/chat", json={"question": "Pytanie", "session_token": "token"}
        )
        assert response.status_code == 503

    def test_chat_route_is_registered(self, client: TestClient) -> None:
        response = client.get("/openapi.json")
        assert "/chat" in response.json()["paths"]


class TestServiceErrorTranslation:
    """A generic driver failure, distinct from the lost-insert-race case
    covered under real-database tests, must still become
    ChatServiceUnavailable rather than leaking SQLAlchemyError."""

    def test_a_lookup_failure_becomes_a_domain_exception(self) -> None:
        class BrokenSession:
            def execute(self, *_args: object, **_kwargs: object) -> None:
                raise SQLAlchemyError("connection reset")

        with pytest.raises(ChatServiceUnavailable):
            get_or_create_chat_session(BrokenSession(), "token")  # type: ignore[arg-type]

    def test_a_flush_failure_becomes_a_domain_exception(self) -> None:
        class NoMatch:
            def scalar_one_or_none(self) -> None:
                return None

        class BrokenSession:
            def execute(self, *_args: object, **_kwargs: object) -> NoMatch:
                return NoMatch()

            def add(self, _instance: object) -> None:
                pass

            def flush(self) -> None:
                raise SQLAlchemyError("connection reset")

        with pytest.raises(ChatServiceUnavailable):
            get_or_create_chat_session(BrokenSession(), "token")  # type: ignore[arg-type]

    def test_a_commit_failure_becomes_a_domain_exception(self) -> None:
        class BrokenSession:
            def add(self, _instance: object) -> None:
                pass

            def commit(self) -> None:
                raise SQLAlchemyError("connection reset")

        chat_session = ChatSession(id=1, token="t")
        with pytest.raises(ChatServiceUnavailable):
            record_query(BrokenSession(), chat_session, "Pytanie")  # type: ignore[arg-type]


@pytest.mark.integration
class TestChatServiceAgainstRealDatabase:
    def test_reusing_a_session_bumps_last_active_at(
        self, migrated_database: None, db_session: Session
    ) -> None:
        token = _unique_token("bump")

        first = get_or_create_chat_session(db_session, token)
        first_seen = first.last_active_at

        second = get_or_create_chat_session(db_session, token)

        assert second.id == first.id
        assert second.last_active_at > first_seen

    def test_recovers_when_another_request_wins_the_insert_race(
        self, monkeypatch: pytest.MonkeyPatch, migrated_database: None
    ) -> None:
        """Simulates two requests racing on the same brand-new token: this
        session's own lookup misses, same as it would if it ran concurrently
        with another request that committed the row a moment earlier."""
        token = _unique_token("race")

        with SessionLocal() as winner:
            winner.add(ChatSession(token=token))
            winner.commit()

        real_find_by_token = chat_service._find_by_token
        calls = {"n": 0}

        def flaky_find(session: Session, tok: str) -> ChatSession | None:
            calls["n"] += 1
            if calls["n"] == 1:
                return None
            return real_find_by_token(session, tok)

        monkeypatch.setattr(chat_service, "_find_by_token", flaky_find)

        with SessionLocal() as loser:
            result = get_or_create_chat_session(loser, token)

        assert result.token == token
        assert calls["n"] == 2


@pytest.mark.integration
class TestChatEndpointAgainstRealDatabase:
    def test_streams_a_non_empty_answer(
        self, migrated_database: None, raw_client: TestClient
    ) -> None:
        response = raw_client.post(
            "/chat",
            json={
                "question": "Czy dwujezycznosc szkodzi dziecku?",
                "session_token": _unique_token("stream"),
            },
        )
        assert response.status_code == 200
        assert response.text.strip() != ""

    def test_the_question_is_persisted_with_no_answer_yet(
        self, migrated_database: None, raw_client: TestClient, db_session: Session
    ) -> None:
        token = _unique_token("persist")
        question = "Jak wspierac dwujezycznosc w domu?"

        response = raw_client.post(
            "/chat", json={"question": question, "session_token": token}
        )
        assert response.status_code == 200

        saved = db_session.execute(
            select(Query).join(ChatSession).where(ChatSession.token == token)
        ).scalar_one()
        assert saved.question == question
        assert saved.answer is None
        assert saved.knowledge_base_version_id is None

    def test_repeated_requests_share_one_chat_session(
        self, migrated_database: None, raw_client: TestClient, db_session: Session
    ) -> None:
        token = _unique_token("shared")
        raw_client.post(
            "/chat", json={"question": "Pierwsze pytanie", "session_token": token}
        )
        raw_client.post(
            "/chat", json={"question": "Drugie pytanie", "session_token": token}
        )

        sessions = (
            db_session.execute(select(ChatSession).where(ChatSession.token == token))
            .scalars()
            .all()
        )
        assert len(sessions) == 1

        queries = (
            db_session.execute(
                select(Query).join(ChatSession).where(ChatSession.token == token)
            )
            .scalars()
            .all()
        )
        assert len(queries) == 2
