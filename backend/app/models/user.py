"""Accounts. Identity only, no authentication logic."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import PERSONAL_DATA, Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.chat import ChatSession


class User(TimestampMixin, Base):
    """A parent with an account.

    An account exists to unlock the larger question quota (D5). Anonymous use
    needs no row here, only a session, which is why `ChatSession.user_id` is
    nullable rather than this table being on the critical path.

    Password hashing is not implemented: this is the column it will write to.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    # 320 is the RFC 5321 maximum. Uniqueness is a database constraint, not an
    # application check: a check-then-insert races, a unique index does not.
    email: Mapped[str] = mapped_column(
        String(320), nullable=False, unique=True, info=PERSONAL_DATA
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, info=PERSONAL_DATA)

    # Verification state as a timestamp rather than a boolean: "verified" and
    # "when" are the same question, and the answer is needed for retention.
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sessions: Mapped[list[ChatSession]] = relationship(back_populates="user")
