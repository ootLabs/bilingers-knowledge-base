"""Panel accounts: the foundation's editors, their sessions and the login audit.

Deliberately separate from `users` (T-82 says so in as many words). A parent's
account unlocks a larger question quota; an editor's account unlocks 30 years
of research covered by an NDA. Same word, different threat model, different
lifecycle, different columns. One table for both would mean any bug on the
quota path is a knowledge base leak.

Nothing here is created by self-service. The panel is expected to hold three to
five accounts for the whole life of the project, so a registration form would
be attack surface bought for no benefit: an administrator creates the account
and hands over a one-time token, and the person sets their own password with
it. That is why `password_hash` is nullable - a real account state, not a
placeholder, and the one state that must never be able to log in.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import PERSONAL_DATA, Base, TimestampMixin


class PanelRole(StrEnum):
    """What an account may do in the panel.

    Two roles, not a permission matrix. The whole difference is who may touch
    other people's accounts, and inventing finer grades for five users would be
    configuration nobody ever reads.
    """

    ADMIN = "admin"
    EDITOR = "editor"


class PanelUser(TimestampMixin, Base):
    """One person with access to the panel.

    `failed_login_count` and `locked_until` live on the account rather than
    being counted from `panel_login_attempts` at login time: the attempt log is
    an append-only audit trail whose retention is not settled (B-07), and a
    lockout that stops working the day someone prunes that table is not a
    lockout.
    """

    __tablename__ = "panel_users"

    id: Mapped[int] = mapped_column(primary_key=True)

    # 320 is the RFC 5321 maximum, matching `users.email`. Stored lowercased by
    # the service layer, so the unique constraint is what actually prevents two
    # accounts differing only in capitalisation.
    email: Mapped[str] = mapped_column(
        String(320), nullable=False, unique=True, info=PERSONAL_DATA
    )

    # Nullable: an account created by an administrator has no password until
    # its owner sets one. `verify_password` refuses a null hash outright, so
    # such an account cannot be logged into, only set up.
    password_hash: Mapped[str | None] = mapped_column(String(255), info=PERSONAL_DATA)

    role: Mapped[PanelRole] = mapped_column(
        Enum(
            PanelRole,
            name="panel_user_role",
            # Without this Postgres stores the member names ("ADMIN"), not the
            # values the API and the frontend speak in.
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=PanelRole.EDITOR,
        server_default=PanelRole.EDITOR.value,
    )

    # Deactivation instead of deletion: the login audit and (once T-89 lands)
    # the change journal have to keep pointing at a real account after someone
    # leaves the foundation.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    failed_login_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sessions: Mapped[list[PanelSession]] = relationship(
        back_populates="panel_user", cascade="all, delete-orphan"
    )
    password_resets: Mapped[list[PanelPasswordReset]] = relationship(
        back_populates="panel_user", cascade="all, delete-orphan"
    )

    @property
    def has_password(self) -> bool:
        """False while the account is still waiting for its owner to set one."""
        return self.password_hash is not None


class PanelSession(Base):
    """One logged-in browser, until it expires or is revoked.

    The token itself is never stored: `token_hash` holds its SHA-256, so a
    database dump does not hand over live sessions. Losing the plaintext is the
    point, and it is why logging in returns the token exactly once.

    Expiry is absolute, not idle-based. A sliding window would write to this
    table on every request to the most sensitive screen in the system, and an
    editor who leaves a tab open on a shared machine would stay logged in for
    as long as the tab lives.
    """

    __tablename__ = "panel_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)

    # CASCADE, unlike `chat_sessions.user_id`: there is no history worth
    # keeping here. Accounts are deactivated rather than deleted anyway, and a
    # session that outlived its account would be a credential with no owner.
    panel_user_id: Mapped[int] = mapped_column(
        ForeignKey("panel_users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # 64 hex characters is exactly SHA-256.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Set on logout, on a password change and on deactivation. A revoked row is
    # kept rather than deleted so "when did this session end" stays answerable.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 45 characters fits an IPv4-mapped IPv6 address, the longest form there is.
    ip_address: Mapped[str | None] = mapped_column(String(45), info=PERSONAL_DATA)
    user_agent: Mapped[str | None] = mapped_column(String(255), info=PERSONAL_DATA)

    panel_user: Mapped[PanelUser] = relationship(back_populates="sessions")


class PanelLoginAttempt(Base):
    """Every attempt to log into the panel, successful or not.

    Append-only, and written even when the email matches no account: an attack
    on a panel with five accounts looks exactly like repeated failures against
    addresses that do not exist, and that pattern is invisible if only real
    accounts are logged.

    `email` is stored as typed rather than as a foreign key, because the rows
    that matter most are the ones with no account behind them.
    """

    __tablename__ = "panel_login_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)

    email: Mapped[str] = mapped_column(
        String(320), nullable=False, index=True, info=PERSONAL_DATA
    )
    # SET NULL rather than CASCADE: deleting an account must not quietly erase
    # the record of who tried to get into it.
    panel_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("panel_users.id", ondelete="SET NULL"), index=True
    )

    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Plain text, not an enum type: this is an audit table, and a new failure
    # reason should never need an ALTER TYPE and a migration to be recordable.
    # The values live in `app.services.panel_auth.LoginFailure`.
    reason: Mapped[str | None] = mapped_column(String(32))

    ip_address: Mapped[str | None] = mapped_column(String(45), info=PERSONAL_DATA)
    user_agent: Mapped[str | None] = mapped_column(String(255), info=PERSONAL_DATA)

    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class PanelPasswordReset(Base):
    """A one-time token that lets its holder set the password of one account.

    Covers both cases: the first password after an administrator creates the
    account, and a reset after one is forgotten. They are the same operation, so
    they are the same row; whether an account has ever had a password is already
    answered by `PanelUser.has_password`.

    Single use and time limited. `used_at` is what makes it single use, and it
    is kept instead of being deleted so a token that shows up twice is visible
    rather than merely refused.
    """

    __tablename__ = "panel_password_resets"

    id: Mapped[int] = mapped_column(primary_key=True)

    panel_user_id: Mapped[int] = mapped_column(
        ForeignKey("panel_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    panel_user: Mapped[PanelUser] = relationship(back_populates="password_resets")
