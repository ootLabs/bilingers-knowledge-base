"""Document content and its version history."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.knowledge import KnowledgeBaseVersion


class DocumentStatus(StrEnum):
    """Where one version stands in the foundation's editorial workflow."""

    DRAFT = "draft"
    IN_REVIEW = "in_review"
    PUBLISHED = "published"
    WITHDRAWN = "withdrawn"


class Document(Base):
    """A document's stable identity. Never updated; every change is a new version."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentVersion(Base):
    """One immutable snapshot of a document's content.

    Editing a document never updates a row here, it inserts a new one. Without
    that, a factual error cannot be rolled back and a quality regression in the
    assistant's answers cannot be investigated (T-37).
    """

    __tablename__ = "document_versions"
    __table_args__ = (
        # Versions are numbered for people, starting at 1. A zero or a negative
        # number would make "the previous version" arithmetic silently wrong.
        CheckConstraint(
            "version_number >= 1", name="document_versions_version_number_positive"
        ),
        UniqueConstraint(
            "document_id", "version_number", name="document_versions_document_id_version_number_key"
        ),
        # The card's second invariant as a database rule: a document may have at
        # most one published version, so "what does the chat read" has exactly
        # one answer. A service-level check would race between two publishes.
        Index(
            "document_versions_one_published_per_document",
            "document_id",
            unique=True,
            # Both dialects, on purpose. `postgresql_where` alone compiles to an
            # unconditional UNIQUE (document_id) everywhere else, so the SQLite
            # fixture the behaviour tests use (`panel_db`) would refuse a second
            # version of a document outright.
            postgresql_where=text("status = 'published'"),
            sqlite_where=text("status = 'published'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # No index of its own: the unique constraint above already indexes
    # document_id as its leading column, and this table is written far more
    # often than it is queried.
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )

    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[DocumentStatus] = mapped_column(
        Enum(
            DocumentStatus,
            name="document_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=DocumentStatus.DRAFT,
        server_default=DocumentStatus.DRAFT.value,
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)

    author_id: Mapped[int | None] = mapped_column(
        ForeignKey("panel_users.id", ondelete="SET NULL"), index=True
    )

    change_comment: Mapped[str | None] = mapped_column(Text)

    knowledge_base_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_base_versions.id", ondelete="RESTRICT"), index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Who put this in front of parents, and when (T-88). Separate from
    # `created_at` and `author_id` because they answer a different question: a
    # version written on Monday and published on Friday by somebody else is the
    # normal case, not the exception.
    #
    # On the row rather than derived from the change journal (T-89), for the
    # same reason the login counters live on `panel_users` rather than being
    # counted from `panel_login_attempts`: the journal's retention is still open
    # (B-07), and "who published what parents are reading" must not stop being
    # answerable the day somebody prunes it.
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # SET NULL, matching `author_id`: accounts are deactivated rather than
    # deleted, but if one ever is, the publication itself still happened.
    published_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("panel_users.id", ondelete="SET NULL"), index=True
    )

    document: Mapped[Document] = relationship(back_populates="versions")

    knowledge_base_version: Mapped[KnowledgeBaseVersion | None] = relationship(
        back_populates="document_versions"
    )
