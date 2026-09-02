from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, read from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Bilingers API"
    database_url: str = "postgresql+psycopg://bilingers:bilingers@db:5432/bilingers"
    cors_origins: str = "http://localhost:3000"
    log_level: str = "info"

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

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
