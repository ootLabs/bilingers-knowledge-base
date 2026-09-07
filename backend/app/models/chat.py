"""Conversations and the per-question cost ledger."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import PERSONAL_DATA, Base

if TYPE_CHECKING:
    from app.models.knowledge import KnowledgeBaseVersion, KnowledgeGap
    from app.models.user import User


class ChatSession(Base):
    """One conversation, whether or not anyone is logged in.

    `user_id` is nullable on purpose. The quota in D5 has to count anonymous
    parents too, and a limit that only applies to accounts is not a limit. The
    thing being counted is `token`, an opaque identifier the client presents,
    so counting works with no account and no personal details.

    That token is pseudonymous rather than anonymous, so it is marked as
    personal data: under GDPR a client-side identifier can identify a person.
    """

    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)

    token: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, info=PERSONAL_DATA
    )

    # SET NULL, not CASCADE: erasing a person must not erase the cost history
    # attributed to their questions. The session survives, detached.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Drives quota windows: a per-day limit needs to know when the day was.
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User | None] = relationship(back_populates="sessions")
    queries: Mapped[list[Query]] = relationship(
        back_populates="chat_session", cascade="all, delete-orphan"
    )


class Query(Base):
    """One question, its answer, and what answering it cost.

    Append-only. This table is the evidence behind cost control (D11, T-41) and
    behind quality regression testing, and an edited ledger is not evidence,
    which is why there is no `updated_at`.

    The measurement columns are nullable because not every question reaches a
    model: an off-topic question is rejected by retrieval, and one over quota is
    rejected before that. Both are still worth a row.

    The row is written before the answer streams and its measurement is filled
    in afterwards, which is completing a row rather than editing one:
    `app.services.usage.record_usage` refuses a second write, so a retry cannot
    double-count or replace a cost that was already reported.
    """

    __tablename__ = "queries"
    __table_args__ = (
        # The acceptance criterion "every answer states which version of the
        # base produced it" as a database rule rather than a convention: an
        # answer with no version would make regression analysis impossible the
        # moment the base changes, and Justyna expects it to change forever.
        CheckConstraint(
            "answer IS NULL OR knowledge_base_version_id IS NOT NULL",
            name="queries_answer_requires_kb_version",
        ),
        # "Summable per model" is a promise the report makes to the foundation,
        # so a cost with no model to attribute it to is refused here rather
        # than discovered later as a row that quietly falls out of a GROUP BY.
        CheckConstraint(
            "cost_pln IS NULL OR (model IS NOT NULL "
            "AND input_tokens IS NOT NULL AND output_tokens IS NOT NULL)",
            name="queries_cost_requires_model",
        ),
        # A PLN figure is only reproducible with the rate and the price list
        # that produced it, and both move. All four travel together or none do.
        CheckConstraint(
            "(cost_pln IS NULL AND cost_usd IS NULL "
            "AND fx_rate_pln_per_usd IS NULL AND pricing_version IS NULL) "
            "OR (cost_pln IS NOT NULL AND cost_usd IS NOT NULL "
            "AND fx_rate_pln_per_usd IS NOT NULL AND pricing_version IS NOT NULL)",
            name="queries_cost_requires_pricing_provenance",
        ),
        # A negative token count or cost is not a small error in a budget
        # report, it is a number that hides another number by cancelling it.
        CheckConstraint(
            "(input_tokens IS NULL OR input_tokens >= 0) "
            "AND (output_tokens IS NULL OR output_tokens >= 0) "
            "AND (cost_usd IS NULL OR cost_usd >= 0) "
            "AND (cost_pln IS NULL OR cost_pln >= 0) "
            "AND (fx_rate_pln_per_usd IS NULL OR fx_rate_pln_per_usd > 0) "
            "AND (duration_ms IS NULL OR duration_ms >= 0)",
            name="queries_measurements_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    chat_session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    knowledge_base_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_base_versions.id", ondelete="RESTRICT"), index=True
    )

    # Free text written by a parent, so it may contain details about a child
    # that nobody asked for. Personal data by default, both directions.
    question: Mapped[str] = mapped_column(Text, nullable=False, info=PERSONAL_DATA)
    answer: Mapped[str | None] = mapped_column(Text, info=PERSONAL_DATA)

    model: Mapped[str | None] = mapped_column(String(100))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    # Fixed point, never a float: this figure is reported to the foundation.
    # Both currencies are kept: the provider invoices in USD, so that column is
    # what reconciles against the bill, while the foundation approves and reads
    # PLN. Deriving one from the other at report time is not equivalent,
    # because the rate on the day of the query is the only honest one.
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    cost_pln: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    fx_rate_pln_per_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    # Which price list produced the figures above, so a number reported months
    # ago can still be traced to the prices behind it.
    pricing_version: Mapped[str | None] = mapped_column(String(50))
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    chat_session: Mapped[ChatSession] = relationship(back_populates="queries")
    knowledge_base_version: Mapped[KnowledgeBaseVersion | None] = relationship(
        back_populates="queries"
    )
    knowledge_gap: Mapped[KnowledgeGap | None] = relationship(back_populates="query")
