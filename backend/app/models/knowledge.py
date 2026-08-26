"""Knowledge base versions and the queue of questions it could not answer."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import PERSONAL_DATA, Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.chat import Query


class KnowledgeGapStatus(StrEnum):
    """Where a reported gap stands in the foundation's workflow (D2)."""

    NEW = "new"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


class KnowledgeBaseVersion(Base):
    """One ingest of the foundation's knowledge base.

    Exists so an answer can be traced back to the exact content that produced
    it. Without that, the first change to the base makes every earlier answer
    unexplainable, and quality regression cannot be measured at all.
    """

    __tablename__ = "knowledge_base_versions"

    id: Mapped[int] = mapped_column(primary_key=True)

    version: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # Hex SHA-256 of the source file, so "is this the same input we ingested
    # last time" is answerable without keeping a copy of the file itself.
    source_checksum: Mapped[str] = mapped_column(String(64), nullable=False)

    # passive_deletes="all" leaves the delete entirely to PostgreSQL. Without
    # it SQLAlchemy helpfully nulls the foreign keys first, so the RESTRICT
    # never fires and deleting a version quietly erases the provenance of every
    # answer it produced, which is the one thing this table exists to prevent.
    queries: Mapped[list[Query]] = relationship(
        back_populates="knowledge_base_version", passive_deletes="all"
    )


class KnowledgeGap(Base, TimestampMixin):
    """A question the knowledge base could not answer.

    The growth loop from D2: no answer means the question goes to the
    foundation, an author fills it in, and the base gets bigger. Status tracks
    that trip.

    `question` intentionally duplicates the text on the related query. The
    guidance in `docs/llm/unanswered-questions.md` is to store the question and
    not the person, so this row has to stay useful after the query and its
    session have been erased, which is also why `query_id` clears rather than
    cascades.
    """

    __tablename__ = "knowledge_gaps"
    __table_args__ = (
        # One query produces at most one gap; the constraint is what makes the
        # relationship a genuine one-to-one rather than an assumption.
        UniqueConstraint("query_id", name="knowledge_gaps_query_id_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    query_id: Mapped[int | None] = mapped_column(ForeignKey("queries.id", ondelete="SET NULL"))

    question: Mapped[str] = mapped_column(Text, nullable=False, info=PERSONAL_DATA)
    status: Mapped[KnowledgeGapStatus] = mapped_column(
        # values_callable, or Postgres stores the member names ("IN_PROGRESS")
        # instead of the values the rest of the system uses.
        Enum(
            KnowledgeGapStatus,
            name="knowledge_gap_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=KnowledgeGapStatus.NEW,
        server_default=KnowledgeGapStatus.NEW.value,
        index=True,
    )

    query: Mapped[Query | None] = relationship(back_populates="knowledge_gap")
