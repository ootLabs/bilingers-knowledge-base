"""document publication

Adds who published a version and when. Both are on the row rather than derived
from the change journal (T-89), because that journal's retention is still an
open question (B-07) and "who published what parents are reading" has to stay
answerable after it is pruned.

Revision ID: 4f1c8a2b9d37
Revises: ebedc16a4160
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4f1c8a2b9d37"
down_revision: str | None = "ebedc16a4160"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document_versions",
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "document_versions",
        sa.Column("published_by_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "document_versions_published_by_id_fkey",
        "document_versions",
        "panel_users",
        ["published_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_document_versions_published_by_id"),
        "document_versions",
        ["published_by_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_document_versions_published_by_id"), table_name="document_versions")
    op.drop_constraint(
        "document_versions_published_by_id_fkey", "document_versions", type_="foreignkey"
    )
    op.drop_column("document_versions", "published_by_id")
    op.drop_column("document_versions", "published_at")
