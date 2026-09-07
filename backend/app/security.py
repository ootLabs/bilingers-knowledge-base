"""Password hashing and one-time tokens.

Primitives only, next to `config.py` and `db.py` rather than under `services/`:
nothing here knows about the panel, about roles or about the database. The
domain rules that use them live in `app.services.panel_auth`.
"""

from __future__ import annotations

import hashlib
import secrets
from functools import lru_cache

import bcrypt

# bcrypt hashes at most 72 bytes and silently ignores the rest, so a longer
# password would be accepted at signup and then be equivalent to its own first
# 72 bytes. The boundary schema rejects anything longer instead of letting that
# happen quietly; this constant is what it measures against.
MAX_PASSWORD_BYTES = 72

# Twelve characters, not eight. These accounts are the only door to the
# foundation's knowledge base and there are five of them, so the usual argument
# for a low floor (support cost across thousands of users) does not apply.
MIN_PASSWORD_LENGTH = 12

# Cost 12: roughly a quarter of a second per attempt on current hardware. The
# panel handles a handful of logins a day, so paying that is free here, while
# it multiplies the cost of an offline attack on a stolen dump.
_BCRYPT_ROUNDS = 12


@lru_cache(maxsize=None)
def _absent_password_hash(rounds: int) -> bytes:
    """A hash nothing can match, cached per cost.

    Compared against when an account has no password, so a request for a
    nonexistent or not-yet-set-up account costs the same time as a real one.
    Computed on first use rather than at import, and keyed by cost, so lowering
    the cost actually lowers it: a constant fixed at import would keep every
    such comparison at production cost no matter what the caller configured.

    Hex, not raw bytes, and that is not cosmetic: raw 32 bytes contain a NUL
    roughly one time in eight. The bcrypt in use hashes those without
    complaint, but this is the unknown-account path, the one whose whole job is
    to cost the same as a real comparison, and `lru_cache` does not cache
    exceptions - so a future version that refused a NUL byte would turn it into
    an intermittent 500 that says "no such account" out loud. 64 hex characters
    are still well inside the 72 bytes bcrypt reads.
    """
    return bcrypt.hashpw(secrets.token_hex(32).encode("ascii"), bcrypt.gensalt(rounds))


# 32 bytes of entropy, URL-safe. Session and password-reset tokens are the only
# credential their holder has, and both travel in a URL or a header.
_TOKEN_BYTES = 32


def hash_password(password: str) -> str:
    """Hash a password for storage. Raises `ValueError` past the bcrypt limit."""
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        # Never truncate to fit: that would store a weaker password than the
        # one the person chose, without telling them.
        raise ValueError("password exceeds the maximum length bcrypt can hash")
    return bcrypt.hashpw(encoded, bcrypt.gensalt(_BCRYPT_ROUNDS)).decode("ascii")


def verify_password(password: str, password_hash: str | None) -> bool:
    """Check a password against a stored hash.

    A missing hash (an account whose owner has not set a password yet) is a
    failure, not a free pass, and still runs a full bcrypt comparison: an
    attacker must not be able to tell "no such account" from "wrong password"
    by timing the answer.

    An oversized password is rejected here as well, so a caller cannot smuggle
    one past `hash_password` by going straight to verification.
    """
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        bcrypt.checkpw(b"", _absent_password_hash(_BCRYPT_ROUNDS))
        return False
    if password_hash is None:
        bcrypt.checkpw(encoded, _absent_password_hash(_BCRYPT_ROUNDS))
        return False
    return bcrypt.checkpw(encoded, password_hash.encode("ascii"))


def new_token() -> str:
    """Mint a session or password-reset token. Shown once, never stored."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_token(token: str) -> str:
    """Hex SHA-256 of a token, which is the only form the database ever holds.

    Plain SHA-256 rather than bcrypt on purpose: unlike a password, a token is
    32 random bytes, so there is nothing to guess and no reason to make every
    authenticated request pay for a slow hash.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
