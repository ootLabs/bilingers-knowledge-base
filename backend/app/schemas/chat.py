"""Request and response shapes for the `/chat` endpoint."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# 32 lowercase hex characters is exactly uuid4().hex - the shape a client is
# expected to mint one of. Anything shorter or non-hex is rejected outright:
# this token is the only key to a conversation, it doubles as the future D5
# quota key, and `queries.question` behind it is marked PERSONAL_DATA, so a
# short or guessable token lets one client collide into another's history.
_SESSION_TOKEN_PATTERN = r"^[0-9a-f]{32,64}$"


class ChatRequest(BaseModel):
    """One question posted to a conversation.

    `session_token` is the opaque, client-generated identifier stored on
    `ChatSession.token` (see `app.models.chat`): the client mints it once per
    conversation, typically `uuid4().hex`, and keeps presenting it, so
    history and quota work without an account.
    """

    # Strips before length constraints are checked, not after: a Field-level
    # max_length is enforced before an ordinary field_validator would run,
    # so a hand-rolled strip-then-check validator would reject a question
    # that only *looks* oversized because of a few stray leading/trailing
    # spaces. This also makes an all-whitespace value fail min_length on its
    # own, no separate blank check needed.
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=4000)
    session_token: str = Field(pattern=_SESSION_TOKEN_PATTERN)
