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
