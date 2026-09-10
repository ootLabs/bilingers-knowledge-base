"""The panel's second factor: enrolling, verifying, recovering (T-83).

TOTP rather than SMS, and not only for the cost. SMS would put an editor's
phone number in this database, which is more personal data in a project whose
GDPR work has not started (B-07), plus a dependency on an operator. TOTP costs
nothing, depends on nobody, and stores no new personal data beyond the secret.

Every attempt at the second factor goes through the same limits as a password:
the per-IP throttle in front of the login endpoint and the per-account lockout
behind it. Six digits are guessable in a million tries; without that, a second
factor is a weaker one, not a second one.

`app.services.panel_auth` calls `verify_second_factor` and nothing else here,
so the dependency runs one way and this module never imports back.

The cryptography and the codes themselves are `app.services.panel_totp`, split
off when this file passed the size limit: that module works on strings and
knows nothing about accounts, this one owns which account has a second factor
and what happens when it is switched on or cleared.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.panel import PanelUser
from app.models.two_factor import PanelBackupCode, PanelTotpSecret
from app.security import hash_token
from app.services.panel_errors import unavailable_on_database_failure
from app.services.panel_totp import (
    decrypt_secret,
    encrypt_secret,
    matched_step,
    new_backup_code,
    new_secret,
    normalise_code,
    provisioning_uri,
)


class TwoFactorAlreadyOn(Exception):
    """This account already has a confirmed second factor."""


class TwoFactorNotEnrolled(Exception):
    """There is nothing to confirm, disable or reset for this account."""


class InvalidSecondFactor(Exception):
    """The code does not open this account."""


@dataclass(frozen=True)
class Enrolment:
    """What the setup screen needs, and the only time the secret is readable."""

    secret: str
    otpauth_uri: str


def _secret_row(session: Session, user: PanelUser) -> PanelTotpSecret | None:
    return session.execute(
        select(PanelTotpSecret).where(PanelTotpSecret.panel_user_id == user.id)
    ).scalar_one_or_none()


@unavailable_on_database_failure
def has_second_factor(session: Session, user: PanelUser) -> bool:
    """Whether logging in as this account needs a code.

    Only a confirmed secret counts. A half-finished enrolment must never gate a
    login, or somebody who closed the tab mid-setup would be locked out of an
    account whose password is perfectly good.
    """
    row = _secret_row(session, user)
    return row is not None and row.confirmed_at is not None


@unavailable_on_database_failure
def begin_enrolment(session: Session, user: PanelUser) -> Enrolment:
    """Mint a secret for this account and hand it over once, unconfirmed.

    Replacing an unconfirmed secret is allowed and expected: somebody who
    abandoned setup half way should be able to start again without an
    administrator. Replacing a confirmed one is not, because that would let
    anyone holding a live session swap out the second factor entirely.
    """
    # Fails here if the deployment has no key, before a secret is minted.
    secret = new_secret()
    encrypted = encrypt_secret(secret)
    existing = _secret_row(session, user)
    if existing is not None and existing.confirmed_at is not None:
        raise TwoFactorAlreadyOn(user.email)

    if existing is None:
        session.add(PanelTotpSecret(panel_user_id=user.id, secret_encrypted=encrypted))
    else:
        existing.secret_encrypted = encrypted
        existing.last_used_step = None
    session.commit()

    return Enrolment(secret=secret, otpauth_uri=provisioning_uri(secret, account=user.email))


def _totp_matches(row: PanelTotpSecret, code: str) -> bool:
    """Check a six-digit code, refusing one that has already been spent.

    Without the step check the same digits work for the whole 30 second window
    they belong to, so anybody who read them over a shoulder gets a second use
    out of them.
    """
    step = matched_step(decrypt_secret(row.secret_encrypted), code)
    if step is None:
        return False
    if row.last_used_step is not None and step <= row.last_used_step:
        return False
    row.last_used_step = step
    return True


def _backup_code_matches(session: Session, user: PanelUser, code: str) -> bool:
    """Spend one printable code, if it is this account's and still unused.

    Looked up by hash, so this is one indexed query rather than a loop over ten
    slow comparisons. The account is checked too: the hash column is unique, but
    matching a row that belongs to somebody else must never open this account.
    """
    normalised = normalise_code(code)
    if not normalised:
        return False
    row = session.execute(
        select(PanelBackupCode).where(PanelBackupCode.code_hash == hash_token(normalised))
    ).scalar_one_or_none()
    if row is None or row.used_at is not None or row.panel_user_id != user.id:
        return False
    row.used_at = datetime.now(UTC)
    return True


def verify_second_factor(session: Session, user: PanelUser, code: str | None) -> bool:
    """Whether this code opens the account. Does not commit.

    The caller (`app.services.panel_auth.login`) commits every exit path,
    successful or not, because the attempt record and the lockout counter are
    part of a failed login too. Spending a backup code has to land on the same
    commit as the session it opened.
    """
    row = _secret_row(session, user)
    if row is None or row.confirmed_at is None:
        # Nothing enrolled, nothing to check. `login` only calls this when
        # `has_second_factor` said otherwise, so this means the row vanished
        # between the two reads.
        return True
    if not code:
        return False
    return _totp_matches(row, code) or _backup_code_matches(session, user, code)


@unavailable_on_database_failure
def confirm_enrolment(session: Session, user: PanelUser, code: str) -> list[str]:
    """Turn the second factor on, and hand back the backup codes once.

    The code is required, so an authenticator that was set up wrong cannot lock
    its owner out: 2FA only starts gating logins after the person has proved,
    with a live code, that their app and this secret agree.
    """
    row = _secret_row(session, user)
    if row is None:
        raise TwoFactorNotEnrolled(user.email)
    if row.confirmed_at is not None:
        raise TwoFactorAlreadyOn(user.email)
    # Through `_totp_matches`, so the step is spent like any other. A raw
    # `verify` here left `last_used_step` NULL, which meant the one code this
    # module ever shows on screen was the one code it did not spend: whoever
    # read it over a shoulder could send it straight to the login endpoint.
    if not _totp_matches(row, code):
        raise InvalidSecondFactor(user.email)

    row.confirmed_at = datetime.now(UTC)
    codes = [new_backup_code() for _ in range(settings.panel_backup_code_count)]
    session.execute(
        PanelBackupCode.__table__.delete().where(PanelBackupCode.panel_user_id == user.id)
    )
    for code_text in codes:
        session.add(
            PanelBackupCode(
                panel_user_id=user.id, code_hash=hash_token(normalise_code(code_text))
            )
        )
    session.commit()
    # Returned in readable form exactly here and nowhere else, the same rule as
    # a session token: only the hashes are kept.
    return codes


@unavailable_on_database_failure
def disable_for_self(session: Session, user: PanelUser, code: str) -> None:
    """Switch the second factor off, proving you can still pass it.

    Requiring a live code means a stolen session cannot quietly remove the thing
    that stops it being useful.
    """
    row = _secret_row(session, user)
    if row is None or row.confirmed_at is None:
        raise TwoFactorNotEnrolled(user.email)
    if not verify_second_factor(session, user, code):
        raise InvalidSecondFactor(user.email)
    _forget(session, user)
    session.commit()


@unavailable_on_database_failure
def reset_for(session: Session, user: PanelUser) -> None:
    """An administrator clears somebody's second factor. The recovery path.

    Deliberately not self-service: a reset link anybody holding the password
    could use is not a second factor. Who did it is in the journal (T-89).
    """
    if _secret_row(session, user) is None:
        raise TwoFactorNotEnrolled(user.email)
    _forget(session, user)
    session.commit()


def _forget(session: Session, user: PanelUser) -> None:
    """Remove this account's secret and every printed code.

    The flush is not optional. `disable_for_self` gets here having just verified
    a code, which leaves an UPDATE pending on the very rows about to be deleted
    (`last_used_step`, or a backup code's `used_at`). The session has
    `autoflush=False`, so without this the bulk DELETE goes first and the commit
    then tries to update rows that no longer exist, which SQLAlchemy refuses
    with a `StaleDataError`.
    """
    session.flush()
    session.execute(
        PanelTotpSecret.__table__.delete().where(PanelTotpSecret.panel_user_id == user.id)
    )
    session.execute(
        PanelBackupCode.__table__.delete().where(PanelBackupCode.panel_user_id == user.id)
    )
    # Nothing is expired afterwards on purpose: every read here goes through a
    # real `SELECT` rather than a primary key lookup, so a deleted row simply
    # does not come back, and expiring the session would surprise the caller
    # that still holds the account object.


@unavailable_on_database_failure
def unused_backup_code_count(session: Session, user: PanelUser) -> int:
    """How many printed codes are still worth anything, for the settings screen."""
    return session.execute(
        select(func.count())
        .select_from(PanelBackupCode)
        .where(
            PanelBackupCode.panel_user_id == user.id,
            PanelBackupCode.used_at.is_(None),
        )
    ).scalar_one()
