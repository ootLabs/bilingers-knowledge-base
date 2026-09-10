from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, read from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Bilingers API"
    database_url: str = "postgresql+psycopg://bilingers:bilingers@db:5432/bilingers"
    cors_origins: str = "http://localhost:3000"
    log_level: str = "info"
    # A file rather than variables, because a price list is a table and because
    # editing it must not need a deploy or even a container restart: the backend
    # mount makes it live, and `app.services.pricing` re-reads it when it
    # changes. Not committed, same as `.env`; copy `backend/pricing.example.json`.
    pricing_file: str = "/app/pricing.json"

    # Panel authentication (T-82). Absolute session lifetime, not idle: 12
    # hours covers a working day and forces a fresh login the next one.
    panel_session_ttl_minutes: int = 720
    # Five wrong passwords, then the account is locked for fifteen minutes.
    # Slow enough to make guessing pointless, short enough that an editor
    # locked out mid-afternoon is not waiting on an administrator.
    panel_login_max_attempts: int = 5
    panel_login_lockout_minutes: int = 15
    # A setup or reset token is handed over by an administrator in person or
    # over chat, so it has to survive until the other person reads it, and no
    # longer.
    panel_password_reset_ttl_hours: int = 24
    # Throttles login attempts by IP address, ahead of the per-account lockout:
    # bcrypt on an unknown address is deliberately paid in full (see
    # `app.services.panel_auth.login`), so nothing else stops a flood of
    # requests from costing CPU. In-process only; see `app.services.rate_limit`.
    panel_login_ip_max_attempts: int = 20
    panel_login_ip_window_minutes: int = 5

    # Largest .docx the panel will read (T-85). Enforced on the server, because
    # a limit that only exists in the upload form is not a limit. 5 MB is a
    # generous chapter of text; far past it means a file full of images, which
    # this reader ignores anyway.
    docx_import_max_bytes: int = 5_242_880

    # Second factor for the panel (T-83). The key that encrypts TOTP secrets at
    # rest. Empty by default and deliberately not given a working fallback: a
    # default key is the same as no key, and it would silently make every
    # deployment's secrets readable from a dump. While it is empty, enrolling in
    # 2FA is refused outright rather than storing a secret in the clear.
    panel_totp_encryption_key: str = ""
    # What the authenticator app shows next to the code, so an editor with three
    # accounts in it can tell which one this is.
    panel_totp_issuer: str = "Bilingers"
    # Printable codes handed over once, when 2FA is switched on.
    panel_backup_code_count: int = 10

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
