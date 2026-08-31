"""Tests for the `/chat` endpoint: request validation, error handling, the
no-orphan write order, and (against real PostgreSQL) actual persistence.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import DataError, IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.chat import ChatSession, Query
from app.routers import chat as chat_router
from app.schemas.chat import ChatRequest
from app.services import chat as chat_service
from app.services.chat import (
    ChatServiceUnavailable,
    InvalidChatInput,
    PLACEHOLDER_CHUNK_COUNT,
    get_or_create_chat_session,
    record_query,
    stream_placeholder_answer,
)

# uuid4().hex: 32 lowercase hex characters, exactly what ChatRequest's
# session_token pattern requires and what a real client is expected to mint.
_VALID_TOKEN = "a" * 32



class TestValidation:
    """These never reach the service layer: Pydantic rejects the body first."""

    def test_blank_question_is_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/chat", json={"question": "   ", "session_token": _VALID_TOKEN}
        )
        assert response.status_code == 422

    def test_missing_session_token_is_rejected(self, client: TestClient) -> None:
        response = client.post("/chat", json={"question": "Pytanie"})
        assert response.status_code == 422

    def test_oversized_question_is_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/chat", json={"question": "a" * 4001, "session_token": _VALID_TOKEN}
        )
        assert response.status_code == 422

    def test_a_question_padded_past_the_limit_is_accepted_after_stripping(self) -> None:
        """max_length is enforced after stripping, not before: a question
        that only *looks* oversized because of stray surrounding whitespace
        must not be rejected for content that fits well under the limit."""
        request = ChatRequest(question=" " + "a" * 3999 + " ", session_token=_VALID_TOKEN)
        assert request.question == "a" * 3999

    def test_an_all_whitespace_question_is_still_rejected(self) -> None:
        with pytest.raises(ValueError, match="question"):
            ChatRequest(question="   ", session_token=_VALID_TOKEN)

    def test_a_short_session_token_is_rejected(self, client: TestClient) -> None:
        """A one-character token would let any two clients collide into the
        same conversation, and `queries.question` behind it is PERSONAL_DATA."""
        response = client.post(
            "/chat", json={"question": "Pytanie", "session_token": "a"}
        )
        assert response.status_code == 422

    def test_a_non_hex_session_token_is_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/chat",
            json={"question": "Pytanie", "session_token": "z" * 32},
        )
        assert response.status_code == 422

    # A valid payload against the stubbed database is covered under
    # TestWiringAndErrors, which mocks the service layer instead of hitting
    # StubSession's minimal, execute()-returns-None interface. Whether it
    # really works against PostgreSQL is TestChatEndpointAgainstRealDatabase.


class TestPlaceholderStream:
    """Pure function, no database: this is the stand-in for T-30/T-40."""

    def test_yields_the_expected_number_of_chunks(self) -> None:
        chunks = list(stream_placeholder_answer("dowolne pytanie"))
        assert len(chunks) == PLACEHOLDER_CHUNK_COUNT

    def test_every_chunk_is_distinct(self) -> None:
        """Nothing repeated or collapsed across the sequence."""
        chunks = list(stream_placeholder_answer("dowolne pytanie"))
        assert len(set(chunks)) == PLACEHOLDER_CHUNK_COUNT


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
            return ChatSession(id=1, token=_VALID_TOKEN)

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
            "/chat", json={"question": "Pytanie", "session_token": _VALID_TOKEN}
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
            "/chat", json={"question": "Pytanie", "session_token": _VALID_TOKEN}
        )
        assert response.status_code == 503
        assert response.json()["detail"] == "database_unavailable"

    def test_invalid_input_becomes_a_422_not_a_503(
        self, monkeypatch: pytest.MonkeyPatch, client: TestClient
    ) -> None:
        def raise_error(_session: object, _token: str) -> ChatSession:
            raise InvalidChatInput("the database rejected the question")

        monkeypatch.setattr(chat_router, "get_or_create_chat_session", raise_error)

        response = client.post(
            "/chat", json={"question": "Pytanie", "session_token": _VALID_TOKEN}
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "invalid_question"

    def test_chat_route_is_registered(self, client: TestClient) -> None:
        response = client.get("/openapi.json")
        assert "/chat" in response.json()["paths"]

    def test_openapi_describes_a_streamed_plain_text_response(
        self, client: TestClient
    ) -> None:
        """Without response_class=StreamingResponse, FastAPI advertises 200
        as application/json with an empty schema - a client generated from
        this spec would call JSON.parse on a plain-text stream and break."""
        chat_op = client.get("/openapi.json").json()["paths"]["/chat"]["post"]
        content = chat_op["responses"]["200"]["content"]
        assert "text/plain" in content
        assert "422" in chat_op["responses"]
        assert "503" in chat_op["responses"]


class _NoMatch:
    def scalar_one_or_none(self) -> None:
        return None


class _NestedTransaction:
    def __enter__(self) -> "_NestedTransaction":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        pass


class FailingSession:
    """A minimal Session double that raises a given exception at exactly one
    call site (`execute`, `begin_nested`, `flush`, or `commit`), and behaves
    like an empty, harmless no-op everywhere else.

    One configurable double instead of a bespoke class per failure point:
    the real `Session` surface these two service functions actually touch is
    small and shared, so there is nothing failure-point-specific to justify
    separate fakes, and a single double is what has to stay in sync with it.
    """

    def __init__(self, error: Exception, fail_on: str) -> None:
        self._error = error
        self._fail_on = fail_on

    def _maybe_raise(self, step: str) -> None:
        if step == self._fail_on:
            raise self._error

    def execute(self, *_args: object, **_kwargs: object) -> _NoMatch:
        self._maybe_raise("execute")
        return _NoMatch()

    def begin_nested(self) -> _NestedTransaction:
        self._maybe_raise("begin_nested")
        return _NestedTransaction()

    def add(self, _instance: object) -> None:
        pass

    def flush(self) -> None:
        self._maybe_raise("flush")

    def commit(self) -> None:
        self._maybe_raise("commit")


class TestServiceErrorTranslation:
    """A generic driver failure, distinct from the lost-insert-race case
    covered under real-database tests, must still become
    ChatServiceUnavailable rather than leaking SQLAlchemyError - except a
    DataError on record_query's commit, which is the client's fault (422)."""

    def test_a_lookup_failure_becomes_a_domain_exception(self) -> None:
        session = FailingSession(SQLAlchemyError("connection reset"), fail_on="execute")
        with pytest.raises(ChatServiceUnavailable):
            get_or_create_chat_session(session, _VALID_TOKEN)  # type: ignore[arg-type]

    def test_a_flush_failure_becomes_a_domain_exception(self) -> None:
        session = FailingSession(SQLAlchemyError("connection reset"), fail_on="flush")
        with pytest.raises(ChatServiceUnavailable):
            get_or_create_chat_session(session, _VALID_TOKEN)  # type: ignore[arg-type]

    def test_a_commit_failure_becomes_a_domain_exception(self) -> None:
        session = FailingSession(SQLAlchemyError("connection reset"), fail_on="commit")
        chat_session = ChatSession(id=1, token=_VALID_TOKEN)
        with pytest.raises(ChatServiceUnavailable):
            record_query(session, chat_session, "Pytanie")  # type: ignore[arg-type]

    def test_a_nul_byte_style_data_error_becomes_invalid_input(self) -> None:
        session = FailingSession(DataError("stmt", {}, Exception("bad byte")), fail_on="commit")
        chat_session = ChatSession(id=1, token=_VALID_TOKEN)
        with pytest.raises(InvalidChatInput):
            record_query(session, chat_session, "Pytanie")  # type: ignore[arg-type]

    def test_a_foreign_key_violation_is_infra_not_client_fault(self) -> None:
        """The only realistic IntegrityError on this insert is the
        chat_session_id foreign key firing because the session vanished
        mid-request - a server-side race, not something a resend fixes."""
        session = FailingSession(
            IntegrityError("stmt", {}, Exception("fk violation")), fail_on="commit"
        )
        chat_session = ChatSession(id=1, token=_VALID_TOKEN)
        with pytest.raises(ChatServiceUnavailable):
            record_query(session, chat_session, "Pytanie")  # type: ignore[arg-type]


@pytest.mark.integration
class TestChatServiceAgainstRealDatabase:
    def test_reusing_a_session_bumps_last_active_at(
        self,
        migrated_database: None,
        db_session: Session,
        committed_token: Callable[[], str],
    ) -> None:
        token = committed_token()

        first = get_or_create_chat_session(db_session, token)
        first_seen = first.last_active_at

        second = get_or_create_chat_session(db_session, token)

        assert second.id == first.id
        assert second.last_active_at > first_seen

    def test_recovers_when_another_request_wins_the_insert_race(
        self,
        monkeypatch: pytest.MonkeyPatch,
        migrated_database: None,
        committed_token: Callable[[], str],
    ) -> None:
        """Simulates two requests racing on the same brand-new token: this
        session's own lookup misses, same as it would if it ran concurrently
        with another request that committed the row a moment earlier."""
        token = committed_token()

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

        with SessionLocal() as winner_readback:
            # The real function, not the module attribute: it is patched to
            # `flaky_find` above, which would consume this as the "miss" call.
            winner_seen = real_find_by_token(winner_readback, token)
            winner_created_at = winner_seen.last_active_at

        with SessionLocal() as loser:
            result = get_or_create_chat_session(loser, token)
            loser.commit()

        assert result.token == token
        assert calls["n"] == 2
        # The recovery path reuses the winner's row - it must count as a
        # reuse for D5's purposes too, same as the non-race reuse branch.
        assert result.last_active_at > winner_created_at

    def test_the_race_recovery_does_not_discard_other_pending_work(
        self,
        monkeypatch: pytest.MonkeyPatch,
        migrated_database: None,
        committed_token: Callable[[], str],
    ) -> None:
        """Regression test for scoping the recovery to a SAVEPOINT: a plain
        session.rollback() here would discard the *whole* transaction, not
        just its own failed insert."""
        race_token = committed_token()
        other_token = committed_token()

        with SessionLocal() as winner:
            winner.add(ChatSession(token=race_token))
            winner.commit()

        real_find_by_token = chat_service._find_by_token
        calls = {"n": 0}

        def flaky_find(session: Session, tok: str) -> ChatSession | None:
            if tok != race_token:
                return real_find_by_token(session, tok)
            calls["n"] += 1
            if calls["n"] == 1:
                return None
            return real_find_by_token(session, tok)

        monkeypatch.setattr(chat_service, "_find_by_token", flaky_find)

        with SessionLocal() as loser:
            # Prior, unrelated work in the same transaction, not yet
            # committed - exactly what an unscoped rollback would discard.
            loser.add(ChatSession(token=other_token))
            loser.flush()

            get_or_create_chat_session(loser, race_token)
            loser.commit()

        with SessionLocal() as verify:
            assert chat_service._find_by_token(verify, other_token) is not None


@pytest.mark.integration
class TestChatEndpointAgainstRealDatabase:
    def test_streams_a_non_empty_answer(
        self,
        migrated_database: None,
        raw_client: TestClient,
        committed_token: Callable[[], str],
    ) -> None:
        response = raw_client.post(
            "/chat",
            json={
                "question": "Czy dwujezycznosc szkodzi dziecku?",
                "session_token": committed_token(),
            },
        )
        assert response.status_code == 200
        assert response.text.strip() != ""

    def test_the_question_is_persisted_with_no_answer_yet(
        self,
        migrated_database: None,
        raw_client: TestClient,
        db_session: Session,
        committed_token: Callable[[], str],
    ) -> None:
        token = committed_token()
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
        self,
        migrated_database: None,
        raw_client: TestClient,
        db_session: Session,
        committed_token: Callable[[], str],
    ) -> None:
        token = committed_token()
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

    def test_a_nul_byte_in_the_question_is_a_422_not_a_503(
        self,
        migrated_database: None,
        raw_client: TestClient,
        db_session: Session,
        committed_token: Callable[[], str],
    ) -> None:
        """Reproduces the exact review finding: PostgreSQL/psycopg refuses a
        NUL byte in a text column, and that must not read as a DB outage."""
        token = committed_token()

        response = raw_client.post(
            "/chat", json={"question": "bad\x00byte", "session_token": token}
        )

        assert response.status_code == 422
        assert response.json()["detail"] == "invalid_question"
        # Atomic: the failed Query insert takes the brand-new ChatSession
        # down with it in the same commit, so nothing is left behind either.
        assert chat_service._find_by_token(db_session, token) is None
