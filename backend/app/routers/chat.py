"""HTTP layer for the `/chat` endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas.chat import ChatRequest
from app.services.chat import (
    ChatServiceUnavailable,
    get_or_create_chat_session,
    record_query,
    stream_placeholder_answer,
)

router = APIRouter(tags=["chat"])


@router.post("/chat")
def chat(payload: ChatRequest, session: Session = Depends(get_session)) -> StreamingResponse:
    """Accept one question and stream back an answer.

    The question is written to the `queries` ledger before this function
    returns, so a connection dropped mid-stream still leaves a row behind
    for T-41 to account for (see `app.services.chat.record_query`). Only the
    streaming itself happens after that point, and a database failure there
    is translated to a proper HTTP status instead of a broken response body.
    """
    try:
        chat_session = get_or_create_chat_session(session, payload.session_token)
        record_query(session, chat_session, payload.question)
    except ChatServiceUnavailable as error:
        raise HTTPException(status_code=503, detail="database unavailable") from error

    return StreamingResponse(stream_placeholder_answer(payload.question), media_type="text/plain")
