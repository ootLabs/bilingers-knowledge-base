"""The panel's change journal (T-89): who did what to the knowledge base.

Separate from `document_versions`, which answers a different question. Versions
say how the CONTENT changed; this says who had ACCESS to it and what they tried
to do with it. During an incident those are two questions with two answers, and
a table that mixed them would answer neither well.

It deliberately does not duplicate `panel_login_attempts`. That table already
records every attempt to get in, including for addresses that match no account,
and writing a second copy of the same fact would mean two tables that can
disagree. This one holds what that table does not: logging out, and everything
done to documents and accounts once inside. The panel's journal view reads both
and merges them (see `app.services.panel_audit`).

Append only. There is no service function that updates or deletes a row here,
and the router exposes no verb that could, including for an administrator: a
journal its subject can edit is not evidence of anything.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import PERSONAL_DATA, Base


class AuditAction:
    """What happened, as stored in `panel_audit_events.action`.

    Values in a plain column rather than a database enum, matching
    `app.services.panel_auth.LoginFailure` and for the same reason: a new thing
    worth recording should never need an `ALTER TYPE` and a migration before it
    can be recorded.

    Logging in is not here. It lives in `panel_login_attempts`, and the two
    constants below name how the journal view labels those rows when it reads
    them, so the frontend has one vocabulary rather than two.
    """

    LOGIN_SUCCEEDED = "login_succeeded"
    LOGIN_FAILED = "login_failed"
    LOGGED_OUT = "logged_out"

    DOCUMENT_CREATED = "document_created"
    DOCUMENT_VERSION_SAVED = "document_version_saved"
    DOCUMENT_VERSION_RESTORED = "document_version_restored"
    DOCUMENT_IMPORTED = "document_imported"
    DOCUMENT_PUBLISHED = "document_published"
    DOCUMENT_WITHDRAWN = "document_withdrawn"

    ACCOUNT_CREATED = "account_created"
    ACCOUNT_CHANGED = "account_changed"
    PASSWORD_RESET_ISSUED = "password_reset_issued"

    TWO_FACTOR_ENABLED = "two_factor_enabled"
    TWO_FACTOR_DISABLED = "two_factor_disabled"
    # An administrator clearing somebody else's second factor. The recovery
    # path, and the one worth being able to point at afterwards.
    TWO_FACTOR_RESET = "two_factor_reset"


class PanelAuditEvent(Base):
    """One thing somebody did in the panel."""

    __tablename__ = "panel_audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    # SET NULL rather than CASCADE, matching `panel_login_attempts`: deleting an
    # account must not quietly erase the record of what it did.
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("panel_users.id", ondelete="SET NULL"), index=True
    )

    # Written as it was at the time, beside the foreign key, so a row stays
    # readable after the account behind it is gone. The same reason
    # `panel_login_attempts` stores the address as typed.
    actor_email: Mapped[str] = mapped_column(String(320), nullable=False, info=PERSONAL_DATA)

    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # What it was done to: "document", "document_version", "panel_user". Free
    # text for the same reason as `action`.
    subject_type: Mapped[str | None] = mapped_column(String(32))
    subject_id: Mapped[int | None] = mapped_column(Integer)

    # Room for one short fact, such as which version number was saved, written
    # as space separated `key=value` pairs (`version=3`, `bytes=4096
    # headings=2`). Keys, not sentences, the same rule the rest of the API
    # follows: the Polish that renders them lives in the frontend dictionary,
    # and English prose here would reach a Polish-only editor untranslated.
    # The login audit's own `reason` values come through this field too, as a
    # bare key with no `=`.
    #
    # Never a copy of the content: this table has to be readable and keepable, and a
    # journal that grows with the size of the documents is neither. It is also
    # not where a parent's question ever goes; conversation retention hangs on
    # GDPR (B-07, T-113).
    detail: Mapped[str | None] = mapped_column(String(255))
