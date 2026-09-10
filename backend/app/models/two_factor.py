"""The panel's second factor (T-83): a TOTP secret and its backup codes.

Taking over an editor's account is a leak of the entire knowledge base. There
is no second line of defence behind the panel: whoever gets in sees everything,
under an NDA that is still open (B-09). That is the whole argument for 2FA here
and against it for parents, whose accounts unlock a question quota (D5).

Two tables rather than columns on `panel_users`: a backup code is one row that
gets spent, so it needs somewhere to be a row, and keeping the secret beside it
means the account table stays about the account.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import PERSONAL_DATA, Base
from app.models.panel import PanelUser


class PanelTotpSecret(Base):
    """One account's authenticator secret.

    Encrypted, not hashed, and that is forced rather than chosen: verifying a
    six-digit code means recomputing it from the secret, so the server has to be
    able to read it back. A hash would make the whole scheme impossible. What
    the encryption buys is that a database dump alone does not hand over the
    second factor, because the key lives in the environment (see
    `PANEL_TOTP_ENCRYPTION_KEY`), not in the database.
    """

    __tablename__ = "panel_totp_secrets"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Unique: one account, one authenticator. Re-enrolling replaces the row
    # rather than adding a second secret that would also open the account.
    # CASCADE, unlike the audit tables: a deleted account's secret is not
    # history worth keeping, it is a live credential with no owner.
    panel_user_id: Mapped[int] = mapped_column(
        ForeignKey("panel_users.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    # A Fernet token: base64, and comfortably inside this bound for a 32 byte
    # secret. Marked as personal data because it is a credential belonging to
    # one named person, the same reason `password_hash` is.
    secret_encrypted: Mapped[str] = mapped_column(String(255), nullable=False, info=PERSONAL_DATA)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Null while enrolment is half done: the secret exists, the person has not
    # yet proved their authenticator agrees with it. An unconfirmed secret must
    # never gate a login, or a failed setup would lock its owner out.
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # The last time step accepted, so the same six digits cannot be replayed
    # inside their own 30 second window by whoever was reading over a shoulder.
    last_used_step: Mapped[int | None] = mapped_column(Integer)

    panel_user: Mapped[PanelUser] = relationship()


class PanelBackupCode(Base):
    """One printable single-use code, for when the phone is not there.

    Stored as a SHA-256 hash, like a session token rather than like a password:
    a backup code is minted with 60 bits of entropy, so there is nothing to
    guess and no reason to make every check pay for bcrypt. Hashing also means
    the lookup is a single indexed query instead of a loop over ten slow
    comparisons.

    `used_at` is what makes a code single use, and the row is kept rather than
    deleted so a code that turns up twice is visible rather than merely refused.
    """

    __tablename__ = "panel_backup_codes"

    id: Mapped[int] = mapped_column(primary_key=True)

    panel_user_id: Mapped[int] = mapped_column(
        ForeignKey("panel_users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # 64 hex characters is exactly SHA-256. Unique, so a lookup by hash needs no
    # account filter to be safe.
    code_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, info=PERSONAL_DATA
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    panel_user: Mapped[PanelUser] = relationship()
