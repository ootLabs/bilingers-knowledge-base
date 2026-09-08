"""panel audit log

The panel's change journal (T-89). Deliberately does not duplicate
`panel_login_attempts`: that table already records every attempt to get in, and
this one holds what it does not. The journal view reads both.

Revision ID: 7b2e5c40a913
Revises: 4f1c8a2b9d37
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7b2e5c40a913"
down_revision: str | None = "4f1c8a2b9d37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "panel_audit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_email", sa.String(length=320), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("subject_type", sa.String(length=32), nullable=True),
        sa.Column("subject_id", sa.Integer(), nullable=True),
        sa.Column("detail", sa.String(length=255), nullable=True),
        # SET NULL, not CASCADE: deleting an account must not erase the record
        # of what it did.
        sa.ForeignKeyConstraint(["actor_id"], ["panel_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_panel_audit_events_occurred_at"), "panel_audit_events", ["occurred_at"]
    )
    op.create_index(op.f("ix_panel_audit_events_actor_id"), "panel_audit_events", ["actor_id"])
    op.create_index(op.f("ix_panel_audit_events_action"), "panel_audit_events", ["action"])


def downgrade() -> None:
    op.drop_index(op.f("ix_panel_audit_events_action"), table_name="panel_audit_events")
    op.drop_index(op.f("ix_panel_audit_events_actor_id"), table_name="panel_audit_events")
    op.drop_index(op.f("ix_panel_audit_events_occurred_at"), table_name="panel_audit_events")
    op.drop_table("panel_audit_events")
