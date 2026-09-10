"""The cryptography and the codes behind the panel's second factor (T-83).

Split from `app.services.panel_two_factor` when that file passed the size
limit, along the seam that was already there: everything here works on strings
and knows nothing about accounts, sessions or the lifecycle of an enrolment.
That module owns which account has a second factor and what happens when it is
switched on; this one owns how a secret is kept, which time step a code belongs
to, and what a printable code looks like.

The dependency runs one way: the lifecycle imports these, never the reverse.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

import pyotp
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

# No I, O, 0 or 1: these are read off paper and typed by hand, and telling them
# apart is exactly the thing people get wrong.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_GROUPS = 3
_GROUP_LENGTH = 4

# TOTP's own step, and the tolerance either side of it. One step is 30 seconds,
# so a window of 1 forgives a phone clock that is up to half a minute out
# without widening the guessing surface to anything that matters.
TOTP_INTERVAL = 30
TOTP_WINDOW = 1


class TwoFactorNotConfigured(Exception):
    """The deployment has no encryption key, so no secret may be stored.

    Lives here because `_cipher` is what raises it. `app.main` translates it to
    one 503 for every route that can reach it.
    """


def _cipher() -> Fernet:
    key = settings.panel_totp_encryption_key.strip()
    if not key:
        # Loud rather than falling back to a default key: a shared default is
        # the same as no encryption, and it would fail silently, which is the
        # worst way for a credential store to fail.
        raise TwoFactorNotConfigured("PANEL_TOTP_ENCRYPTION_KEY is not set")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError) as error:
        raise TwoFactorNotConfigured("PANEL_TOTP_ENCRYPTION_KEY is not a valid key") from error


def new_secret() -> str:
    """A fresh base32 secret, readable exactly once by the caller."""
    return pyotp.random_base32()


def encrypt_secret(secret: str) -> str:
    """Seal a secret for storage. A dump alone must not hand it over."""
    return _cipher().encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_secret(stored: str) -> str:
    """Open a stored secret, or say the key cannot read it."""
    try:
        return _cipher().decrypt(stored.encode("ascii")).decode("ascii")
    except InvalidToken as error:
        # The key changed, or the row came from another environment. Not the
        # caller's fault and not something a different code would fix.
        raise TwoFactorNotConfigured("stored secret cannot be read with this key") from error


def provisioning_uri(secret: str, *, account: str) -> str:
    """The `otpauth://` URI an authenticator app expects.

    The label is percent-encoded, as the Key URI format requires; a reader
    comparing it to an address has to decode it first.
    """
    return pyotp.TOTP(secret, interval=TOTP_INTERVAL).provisioning_uri(
        name=account, issuer_name=settings.panel_totp_issuer
    )


def new_backup_code() -> str:
    groups = [
        "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_GROUP_LENGTH))
        for _ in range(_CODE_GROUPS)
    ]
    return "-".join(groups)


def normalise_code(code: str) -> str:
    """One spelling of a code, whatever the person typed.

    Dashes, spaces and case are how a code gets written down and read back; the
    entropy is in the letters. Stripping them here means the hash is computed on
    the same string at issue time and at use time.
    """
    return "".join(character for character in code.upper() if character.isalnum())


def matched_step(secret: str, code: str) -> int | None:
    """Which time step these digits belong to, or None if they belong to none.

    The step the CODE belongs to, not the step the clock happens to be in, and
    that distinction is the whole point. `verify(valid_window=1)` accepts the
    previous and the next step as well, so recording the current clock step
    would let the same digits through again the moment the clock rolled over:
    used at step N it stored N, and at step N+1 the same code still verified
    and N+1 > N passed the replay check. Sixty seconds of reuse for something
    the comment below promises is single use.
    """
    totp = pyotp.TOTP(secret, interval=TOTP_INTERVAL)
    current = int(datetime.now(UTC).timestamp()) // TOTP_INTERVAL
    for step in range(current - TOTP_WINDOW, current + TOTP_WINDOW + 1):
        # An aware timestamp, so pyotp converts through UTC rather than through
        # the container's local time: the naive path goes via `mktime`, which
        # picks the wrong offset for an ambiguous hour when a DST change lands
        # in it, and every code would be refused for that hour.
        moment = datetime.fromtimestamp(step * TOTP_INTERVAL, UTC)
        if totp.verify(code, for_time=moment):
            return step
    return None
