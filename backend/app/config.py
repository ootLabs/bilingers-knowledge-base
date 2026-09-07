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

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
