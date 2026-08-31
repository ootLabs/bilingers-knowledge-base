"""Request and response shapes for the panel endpoints.

Passwords are validated here rather than deeper in, per `docs/conventions.md`:
the boundary rejects them, and anything past the router is assumed valid.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.panel import PanelRole
from app.security import MAX_PASSWORD_BYTES, MIN_PASSWORD_LENGTH

# Not RFC 5322 in full: that grammar accepts addresses no mail provider issues
# and no human types. This rejects the shapes that are certainly wrong and
# leaves the rest to the fact that an administrator types these by hand for
# people they know by name.
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

Email = Annotated[str, Field(pattern=_EMAIL_PATTERN, max_length=320)]


class _PasswordField(BaseModel):
    """Shared password rule: long enough to matter, short enough for bcrypt."""

    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH)

    @field_validator("new_password")
    @classmethod
    def fits_bcrypt(cls, value: str) -> str:
        # Measured in bytes, not characters: the limit bcrypt silently
        # truncates at is 72 bytes, and Polish letters take two of them each.
        if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(f"password must not exceed {MAX_PASSWORD_BYTES} bytes")
        return value


class PanelLoginRequest(BaseModel):
    """Credentials posted to open a session."""

    email: Email
    # No length floor: the rule for a *new* password does not belong on the
    # login form, where rejecting a short one only tells an attacker that the
    # real password is longer than what they tried.
    password: str = Field(min_length=1, max_length=1024)


class PanelUserResponse(BaseModel):
    """An account as the panel shows it. Never carries a hash or a token."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: PanelRole
    is_active: bool
    # Lets the panel show "invitation pending" without exposing anything about
    # the credential itself.
    has_password: bool
    last_login_at: datetime | None
    created_at: datetime


class PanelSessionResponse(BaseModel):
    """The one and only time a session token is readable."""

    token: str
    expires_at: datetime
    user: PanelUserResponse


class PanelUserCreateRequest(BaseModel):
    email: Email
    role: PanelRole = PanelRole.EDITOR


class PasswordResetResponse(BaseModel):
    """A one-time token an administrator passes to the account's owner.

    Returned in the response body because there is no mail path yet; see
    `app.services.panel_passwords`.
    """

    user: PanelUserResponse
    token: str
    expires_at: datetime


class PanelUserUpdateRequest(BaseModel):
    """Partial update. At least one field, or the request means nothing."""

    role: PanelRole | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def at_least_one_change(self) -> PanelUserUpdateRequest:
        if self.role is None and self.is_active is None:
            raise ValueError("provide role, is_active, or both")
        return self


class PasswordResetConfirmRequest(_PasswordField):
    """Spend a setup or reset token and set the account's password."""

    token: str = Field(min_length=1, max_length=512)


class PasswordChangeRequest(_PasswordField):
    """Change your own password, proving you know the current one."""

    current_password: str = Field(min_length=1, max_length=1024)
