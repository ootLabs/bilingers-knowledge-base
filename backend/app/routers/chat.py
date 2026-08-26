"""HTTP layer for the `/chat` endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas.chat import ChatRequest
from app.services.chat import (
    ChatServiceUnavailable,
    InvalidChatInput,
    get_or_create_chat_session,
    record_query,
    stream_placeholder_answer,
)

router = APIRouter(tags=["chat"])


@router.post(
    "/chat",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "The answer, streamed as plain text one chunk at a time.",
            "content": {"text/plain": {"schema": {"type": "string"}}},
        },
        422: {"description": "The database rejected the input as given."},
        503: {"description": "The database is temporarily unavailable."},
    },
)
def chat(payload: ChatRequest, session: Session = Depends(get_session)) -> StreamingResponse:
    """Accept one question and stream back an answer.

    The question is written to the `queries` ledger before this function
    returns, so a connection dropped mid-stream still leaves a row behind
    for T-41 to account for (see `app.services.chat.record_query`). Only the
    streaming itself happens after that point.

    A database failure is translated to a proper HTTP status instead of a
    broken response body: `InvalidChatInput` means the request itself was
    bad and retrying it unchanged would fail again (422); `ChatServiceUnavailable`
    means the database was unreachable, which retrying might fix (503). The
    `detail` on both is a short key, not a sentence, so it stays translatable
    at the frontend copy layer per `docs/conventions.md`.
    """
    try:
        chat_session = get_or_create_chat_session(session, payload.session_token)
        record_query(session, chat_session, payload.question)
    except InvalidChatInput as error:
        raise HTTPException(status_code=422, detail="invalid_question") from error
    except ChatServiceUnavailable as error:
        raise HTTPException(status_code=503, detail="database_unavailable") from error

    return StreamingResponse(stream_placeholder_answer(payload.question), media_type="text/plain")
