"""Core data model: users, sessions, queries, knowledge base versions and gaps

Revision ID: 0001
Revises:
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KNOWLEDGE_GAP_STATUS = sa.Enum(
    "new",
    "in_progress",
    "resolved",
    name="knowledge_gap_status",
)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "knowledge_base_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("source_checksum", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version"),
    )

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        # Nullable: an anonymous parent still gets a session, because the quota
        # in D5 has to count them too.
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "last_active_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index(op.f("ix_chat_sessions_user_id"), "chat_sessions", ["user_id"])

    op.create_table(
        "queries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chat_session_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_base_version_id", sa.Integer(), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        # An answer with no base version cannot be explained once the base
        # changes, so the database refuses to store one.
        sa.CheckConstraint(
            "answer IS NULL OR knowledge_base_version_id IS NOT NULL",
            name="queries_answer_requires_kb_version",
        ),
        sa.ForeignKeyConstraint(["chat_session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["knowledge_base_version_id"], ["knowledge_base_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_queries_chat_session_id"), "queries", ["chat_session_id"])
    op.create_index(
        op.f("ix_queries_knowledge_base_version_id"), "queries", ["knowledge_base_version_id"]
    )
    op.create_index(op.f("ix_queries_created_at"), "queries", ["created_at"])

    op.create_table(
        "knowledge_gaps",
        sa.Column("id", sa.Integer(), nullable=False),
        # SET NULL, not CASCADE: the queue of what parents ask has to survive
        # erasure of the individual query it came from.
        sa.Column("query_id", sa.Integer(), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", KNOWLEDGE_GAP_STATUS, server_default="new", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["query_id"], ["queries.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("query_id", name="knowledge_gaps_query_id_key"),
    )
    op.create_index(op.f("ix_knowledge_gaps_status"), "knowledge_gaps", ["status"])


def downgrade() -> None:
    op.drop_table("knowledge_gaps")
    op.drop_table("queries")
    op.drop_table("chat_sessions")
    op.drop_table("knowledge_base_versions")
    op.drop_table("users")
    # create_table created the type implicitly; dropping the table does not
    # remove it, so a downgrade followed by an upgrade would fail without this.
    KNOWLEDGE_GAP_STATUS.drop(op.get_bind())
