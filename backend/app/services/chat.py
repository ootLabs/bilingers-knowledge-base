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
from sqlalchemy.exc import DataError, IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.chat import ChatSession, Query


class ChatServiceUnavailable(Exception):
    """An infrastructure failure prevented the chat request from being
    recorded: the database is unreachable, a connection dropped, and so on.
    Not the client's fault - maps to a 503.

    Raised instead of letting `SQLAlchemyError` cross the service boundary,
    so the router only ever translates well-known exceptions into HTTP
    responses (see `docs/conventions.md`: "services raise domain exceptions
    and let the router translate them").
    """


class InvalidChatInput(Exception):
    """The database rejected the input itself, not the connection: a
    constraint violation or data the driver refuses to store (a NUL byte in
    a text column, for one real example). The client's fault - maps to a
    422, not a 503, and is not worth retrying unchanged.
    """


# A sequence of opaque keys, not prose in any language: `docs/conventions.md`
# says the backend returns data and keys, not sentences, and that holds for
# a placeholder same as for real UI copy. Streaming several distinct chunks
# (rather than one) is what proves the transport delivers pieces, not a
# single blob - that mechanic is the entire point of this endpoint today.
# Replaced once T-30/T-40 land: a real answer is per-request model output,
# which is the one thing this product does source as prose from the backend.
PLACEHOLDER_CHUNK_COUNT = 6


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
        try:
            # A SAVEPOINT, not the outer transaction: this call is always
            # the first thing the router does today, so there is nothing
            # else to lose here, but scoping the rollback to just this
            # insert keeps that true even if a future caller writes
            # something before it (quota accounting in T-40/T-41, say).
            with session.begin_nested():
                session.add(chat_session)
                session.flush()
        except IntegrityError as error:
            # Lost a race: two requests on the same brand-new token both
            # missed the lookup above, and the other one committed first.
            # Recover by re-reading it instead of failing a valid question.
            chat_session = _find_by_token(session, token)
            if chat_session is None:  # pragma: no cover - driver-level surprise, not recoverable
                raise ChatServiceUnavailable(
                    "chat session insert conflicted but the token is not readable"
                ) from error
            chat_session.last_active_at = datetime.now(UTC)
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
    except DataError as error:
        # The driver itself refuses this data (a NUL byte in `question` is
        # the real example this was written for) - the client's fault, and
        # retrying the identical request would fail again the same way.
        # IntegrityError is deliberately NOT caught here: the only
        # constraint this insert can realistically violate is the
        # chat_session_id foreign key, which means chat_session vanished
        # between get_or_create_chat_session and this commit - a server-side
        # race, not bad input, so it falls through to ChatServiceUnavailable.
        raise InvalidChatInput("the question could not be stored as given") from error
    except SQLAlchemyError as error:
        raise ChatServiceUnavailable("could not record the question") from error
    return query


def stream_placeholder_answer(question: str) -> Iterator[str]:
    """Yield a few opaque placeholder chunks.

    `question` is accepted but unused for now; it becomes the retrieval
    input once T-30 exists. Keeping the parameter here means the call site
    at the router does not change shape when that lands.

    Never given `session`, on purpose: the request's database session is
    closed as soon as the router returns this generator, before any of these
    chunks are actually sent over the wire (a `Depends(get_session)` yield
    dependency's cleanup runs right after the sync handler returns, not
    after ASGI finishes streaming the body). Fine today, since nothing here
    touches the database - but whatever eventually replaces this generator
    with real per-chunk work (token/cost logging alongside T-30/T-40) needs
    its own session, opened inside the generator, not this one.
    """
    for index in range(PLACEHOLDER_CHUNK_COUNT):
        yield f"chat.placeholder_answer.chunk_{index}\n"
