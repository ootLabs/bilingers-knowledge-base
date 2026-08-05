from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, read from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Bilingers API"
    database_url: str = "postgresql+psycopg://bilingers:bilingers@db:5432/bilingers"
    cors_origins: str = "http://localhost:3000"
    log_level: str = "info"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
