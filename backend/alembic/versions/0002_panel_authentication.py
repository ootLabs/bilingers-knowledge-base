"""Panel accounts: editors, sessions, the login audit and password resets

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PANEL_USER_ROLE = sa.Enum("admin", "editor", name="panel_user_role")


def upgrade() -> None:
    op.create_table(
        "panel_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        # Nullable: an account created by an administrator has no password
        # until its owner sets one with a setup token, and must not be able to
        # log in before that.
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("role", PANEL_USER_ROLE, server_default="editor", nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        # The lockout counter lives on the account, not in the audit table:
        # pruning an audit log must never quietly disable the brute-force
        # limit.
        sa.Column("failed_login_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
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
        "panel_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("panel_user_id", sa.Integer(), nullable=False),
        # SHA-256 of the token, never the token: a database dump must not hand
        # over live sessions.
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["panel_user_id"], ["panel_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_panel_sessions_panel_user_id"), "panel_sessions", ["panel_user_id"])

    op.create_table(
        "panel_login_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        # Stored as typed, with no account behind it when the address is
        # unknown: those are exactly the rows an attack shows up in.
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("panel_user_id", sa.Integer(), nullable=True),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        # Plain text rather than an enum type: a new failure reason must not
        # need an ALTER TYPE to be recordable in an audit table.
        sa.Column("reason", sa.String(length=32), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # SET NULL: deleting an account must not erase the record of who tried
        # to get into it.
        sa.ForeignKeyConstraint(["panel_user_id"], ["panel_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_panel_login_attempts_panel_user_id"), "panel_login_attempts", ["panel_user_id"]
    )
    op.create_index(op.f("ix_panel_login_attempts_email"), "panel_login_attempts", ["email"])
    op.create_index(
        op.f("ix_panel_login_attempts_attempted_at"), "panel_login_attempts", ["attempted_at"]
    )

    op.create_table(
        "panel_password_resets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("panel_user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        # Kept rather than deleted after use, so a token presented twice is
        # visible in the data and not merely refused.
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["panel_user_id"], ["panel_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        op.f("ix_panel_password_resets_panel_user_id"),
        "panel_password_resets",
        ["panel_user_id"],
    )


def downgrade() -> None:
    op.drop_table("panel_password_resets")
    op.drop_table("panel_login_attempts")
    op.drop_table("panel_sessions")
    op.drop_table("panel_users")
    # create_table created the type implicitly; dropping the table does not
    # remove it, so a downgrade followed by an upgrade would fail without this.
    PANEL_USER_ROLE.drop(op.get_bind())
