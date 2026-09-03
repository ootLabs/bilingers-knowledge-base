"""Password hashing and token minting.

No database and no HTTP: these are the primitives everything else in the panel
trusts, and they are worth pinning on their own. The rules asserted here are
the ones whose absence would not fail any other test, only quietly weaken the
system: a salt that does not vary, a missing hash that verifies, a password
long enough for bcrypt to truncate.
"""

from __future__ import annotations

import pytest

from app.security import (
    MAX_PASSWORD_BYTES,
    MIN_PASSWORD_LENGTH,
    hash_password,
    hash_token,
    new_token,
    verify_password,
)

PASSWORD = "poprawne-haslo-panelu"


class TestPasswordHashing:
    def test_the_right_password_verifies(self) -> None:
        assert verify_password(PASSWORD, hash_password(PASSWORD)) is True

    def test_the_wrong_password_does_not(self) -> None:
        assert verify_password("cos-innego-zupelnie", hash_password(PASSWORD)) is False

    def test_the_same_password_hashes_differently_every_time(self) -> None:
        """A shared salt would make two identical passwords visible as such."""
        assert hash_password(PASSWORD) != hash_password(PASSWORD)

    def test_an_account_with_no_password_cannot_be_verified_into(self) -> None:
        """The state an administrator leaves behind must not be a free pass."""
        assert verify_password(PASSWORD, None) is False

    def test_a_password_bcrypt_would_truncate_is_refused_not_shortened(self) -> None:
        """Storing a silently truncated password would be weaker than asked for."""
        too_long = "a" * (MAX_PASSWORD_BYTES + 1)
        with pytest.raises(ValueError):
            hash_password(too_long)

    def test_an_oversized_password_cannot_be_smuggled_past_verification(self) -> None:
        stored = hash_password("a" * MAX_PASSWORD_BYTES)
        assert verify_password("a" * (MAX_PASSWORD_BYTES + 1), stored) is False

    def test_length_is_measured_in_bytes_not_characters(self) -> None:
        """Polish letters cost two bytes each, so 72 characters can exceed 72 bytes."""
        polish = "ą" * 40
        assert len(polish) < MAX_PASSWORD_BYTES < len(polish.encode("utf-8"))
        with pytest.raises(ValueError):
            hash_password(polish)

    def test_the_minimum_length_is_the_one_the_schema_advertises(self) -> None:
        assert MIN_PASSWORD_LENGTH == 12


class TestNulBytes:
    """A NUL byte in a password is neither an error nor a truncation point.

    Nothing rejects one on the way in, deliberately: a password is only ever
    hashed, and the hash it produces is ASCII, so unlike an address it never
    reaches the database as text. That makes this bcrypt's promise rather than
    the schema's, and the promise is worth pinning: raising here would be a
    500 on the login endpoint, and truncating at the NUL would let anything
    starting with one match a hash of the empty string, straight past the
    twelve-character floor.
    """

    def test_a_password_containing_one_verifies_only_against_itself(self) -> None:
        smuggled = "\x00" + "a" * 11
        stored = hash_password(smuggled)
        assert verify_password(smuggled, stored) is True
        assert verify_password("\x00", stored) is False
        assert verify_password("", stored) is False

    def test_the_bytes_after_one_are_not_ignored(self) -> None:
        """The truncation case stated as its own assertion: if bcrypt stopped
        reading at the NUL, these two would hash to the same credential."""
        assert verify_password("\x00" + "a" * 11, hash_password("\x00" + "b" * 11)) is False

    def test_a_missing_hash_is_still_refused_without_raising(self) -> None:
        """The unknown-account path pays for a comparison against a hash of
        random bytes; a NUL in the password offered must not turn that into an
        exception, which would answer "no such account" with a 500."""
        assert verify_password("\x00" + "a" * 11, None) is False


class TestTokens:
    def test_every_token_is_different(self) -> None:
        assert len({new_token() for _ in range(100)}) == 100

    def test_a_token_hashes_to_the_same_value_every_time(self) -> None:
        token = new_token()
        assert hash_token(token) == hash_token(token)

    def test_different_tokens_hash_differently(self) -> None:
        assert hash_token(new_token()) != hash_token(new_token())

    def test_the_hash_fits_the_column(self) -> None:
        """`token_hash` is String(64); a longer digest would be truncated."""
        digest = hash_token(new_token())
        assert len(digest) == 64
        assert set(digest) <= set("0123456789abcdef")

    def test_the_token_itself_is_not_recoverable_from_the_hash(self) -> None:
        token = new_token()
        assert token not in hash_token(token)
