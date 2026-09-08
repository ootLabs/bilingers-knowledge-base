"""document content and versions

Revision ID: ebedc16a4160
Revises: 6059ee904da3
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ebedc16a4160"
down_revision: str | None = "6059ee904da3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DOCUMENT_STATUS = sa.Enum("draft", "in_review", "published", "withdrawn", name="document_status")


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "document_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", DOCUMENT_STATUS, server_default="draft", nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=True),
        sa.Column("change_comment", sa.Text(), nullable=True),
        sa.Column("knowledge_base_version_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        # Versions are numbered for people, starting at 1: a zero or a negative
        # number would make "the previous version" arithmetic silently wrong.
        sa.CheckConstraint(
            "version_number >= 1", name="document_versions_version_number_positive"
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["panel_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["knowledge_base_version_id"], ["knowledge_base_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        # Indexes document_id as its leading column, so the foreign key needs
        # no index of its own.
        sa.UniqueConstraint(
            "document_id", "version_number", name="document_versions_document_id_version_number_key"
        ),
    )
    op.create_index(op.f("ix_document_versions_author_id"), "document_versions", ["author_id"])
    op.create_index(
        op.f("ix_document_versions_knowledge_base_version_id"),
        "document_versions",
        ["knowledge_base_version_id"],
    )
    op.create_index(
        "document_versions_one_published_per_document",
        "document_versions",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("status = 'published'"),
    )


def downgrade() -> None:
    op.drop_table("document_versions")
    op.drop_table("documents")
    # create_table created the type implicitly; dropping the table does not
    # remove it, so a downgrade followed by an upgrade would fail without this.
    DOCUMENT_STATUS.drop(op.get_bind())
