"""panel two factor

TOTP secrets and printable backup codes for panel accounts (T-83).

Revision ID: c9a4d1f6b820
Revises: 7b2e5c40a913
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9a4d1f6b820"
down_revision: str | None = "7b2e5c40a913"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "panel_totp_secrets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("panel_user_id", sa.Integer(), nullable=False),
        sa.Column("secret_encrypted", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_step", sa.Integer(), nullable=True),
        # CASCADE: a secret with no account is a live credential with no owner,
        # not history worth keeping.
        sa.ForeignKeyConstraint(["panel_user_id"], ["panel_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # One account, one authenticator. Re-enrolling replaces this row rather
        # than leaving a second secret that would also open the account.
        sa.UniqueConstraint("panel_user_id", name="panel_totp_secrets_panel_user_id_key"),
    )
    op.create_table(
        "panel_backup_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("panel_user_id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["panel_user_id"], ["panel_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash", name="panel_backup_codes_code_hash_key"),
    )
    op.create_index(
        op.f("ix_panel_backup_codes_panel_user_id"), "panel_backup_codes", ["panel_user_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_panel_backup_codes_panel_user_id"), table_name="panel_backup_codes")
    op.drop_table("panel_backup_codes")
    op.drop_table("panel_totp_secrets")
