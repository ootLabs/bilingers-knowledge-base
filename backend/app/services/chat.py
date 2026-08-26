"""Business logic behind the `/chat` endpoint.

This is the pipe T-12 asks for, not the engine: there is no retrieval
(T-30/T-31), no model orchestration (T-40), and no guardrails (T-50) yet.
`stream_placeholder_answer` stands in for all three so the streaming
mechanics, session handling, and cost ledger can be built and tested before
any of that exists.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.chat import ChatSession, Query


class ChatServiceUnavailable(Exception):
    """A database failure prevented the chat request from being recorded.

    Raised instead of letting `SQLAlchemyError` cross the service boundary,
    so the router only ever translates one well-known exception into an HTTP
    response (see `docs/conventions.md`: "services raise domain exceptions
    and let the router translate them").
    """


# Replaced once T-30/T-40 land. Short on purpose, so a test or a demo run
# finishes in a handful of chunks rather than proving nothing new.
#
# English on purpose, unlike the rest of this product's user-facing text:
# `docs/llm/i18n.md` bans hardcoded Polish in the backend outright ("not in
# the backend, not in error messages returned by the API"). A real answer
# will be Polish because the model generates it per request; this fixed,
# developer-authored string is not that, so it does not get that exemption.
PLACEHOLDER_ANSWER = (
    "This is a placeholder answer from the /chat streaming skeleton (T-12). "
    "No knowledge base retrieval or model call has run yet, see T-30/T-40. "
    "It streams in a few chunks to prove the transport works end to end."
)


def _find_by_token(session: Session, token: str) -> ChatSession | None:
    return session.execute(
        select(ChatSession).where(ChatSession.token == token)
    ).scalar_one_or_none()


def get_or_create_chat_session(session: Session, token: str) -> ChatSession:
    """Look up a conversation by its client-presented token, or start one.

    One token is one conversation for its whole lifetime, so a repeated
    token has to return the same row rather than fork a silent second one.
    Reusing a row bumps `last_active_at`, which is what a future per-day
    quota (D5) would read to know when the day was for this conversation.

    The new-row branch only flushes, it does not commit: `record_query`
    commits both this row and the query together, so a failure partway
    through never leaves a session with no query behind it.
    """
    try:
        chat_session = _find_by_token(session, token)
        if chat_session is not None:
            chat_session.last_active_at = datetime.now(UTC)
            return chat_session

        chat_session = ChatSession(token=token)
        session.add(chat_session)
        try:
            session.flush()
        except IntegrityError:
            # Lost a race: two requests on the same brand-new token both
            # missed the lookup above, and the other one committed first.
            # Recover by re-reading it instead of failing a valid question.
            session.rollback()
            chat_session = _find_by_token(session, token)
            if chat_session is None:  # pragma: no cover - driver-level surprise, not recoverable
                raise ChatServiceUnavailable(
                    "chat session insert conflicted but the token is not readable"
                ) from None
    except SQLAlchemyError as error:
        raise ChatServiceUnavailable("could not create the chat session") from error

    return chat_session


def record_query(session: Session, chat_session: ChatSession, question: str) -> Query:
    """Write the question, and commit, before a single byte of the answer streams out.

    A connection that drops mid-answer must not leave the question unlogged:
    T-41's cost ledger can only account for what this table remembers. This
    commit is the one that makes both this row and `chat_session` (if it was
    just created) durable together, before the response starts streaming and
    no matter how the stream itself ends.

    `answer` stays NULL. No model runs in this endpoint yet, and the
    `queries` table's own constraint requires a knowledge base version
    before an answer can be recorded - the same rule that already covers
    off-topic and over-quota questions that never reach a model (see the
    `Query` docstring in `app.models.chat`).
    """
    query = Query(chat_session_id=chat_session.id, question=question)
    session.add(query)
    try:
        session.commit()
    except SQLAlchemyError as error:
        raise ChatServiceUnavailable("could not record the question") from error
    return query


def stream_placeholder_answer(question: str) -> Iterator[str]:
    """Yield the stand-in answer in a few chunks.

    `question` is accepted but unused for now; it becomes the retrieval
    input once T-30 exists. Keeping the parameter here means the call site
    at the router does not change shape when that lands.
    """
    words = PLACEHOLDER_ANSWER.split(" ")
    chunk_size = 4
    for start in range(0, len(words), chunk_size):
        yield " ".join(words[start : start + chunk_size]) + " "
