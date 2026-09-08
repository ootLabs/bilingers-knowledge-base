"""Request and response shapes for the panel's second factor (T-83)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# Six digits from an authenticator, or a printed backup code with its dashes.
# One field for both, because the person typing it should not have to know which
# kind of code they are holding.
SecondFactorCode = Field(min_length=1, max_length=32)


class TwoFactorStatusResponse(BaseModel):
    """What the settings screen shows about this account's second factor."""

    enabled: bool
    # Zero here means the printed sheet is spent, which is worth saying before
    # the phone is lost rather than after.
    unused_backup_codes: int


class TwoFactorEnrolmentResponse(BaseModel):
    """The one and only time the secret is readable.

    `otpauth_uri` is the standard string an authenticator app expects; `secret`
    is the same value in the form a person types by hand. Both are here because
    this panel shows the key as text rather than as a QR code (no QR library is
    installed, and adding one is a decision for `docs/architecture.md`).
    """

    model_config = ConfigDict(from_attributes=True)

    secret: str
    otpauth_uri: str


class TwoFactorCodeRequest(BaseModel):
    """A code, whether from the app or from the printed sheet."""

    code: str = SecondFactorCode


class BackupCodesResponse(BaseModel):
    """The printable codes, returned once and never readable again."""

    codes: list[str]
