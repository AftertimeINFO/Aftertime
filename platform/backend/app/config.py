from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Aftertime Platform"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://aftertime:aftertime-local@postgres:5432/aftertime"
    # Databases of the prePROD and PROD layers; derived from database_url when empty.
    database_url_preprod: str = ""
    database_url_prod: str = ""
    redis_url: str = "redis://redis:6379/0"
    api_cors_origins: str = "http://localhost:8080,http://localhost:8083,http://localhost:5173"
    sync_poll_seconds: int = 5
    sync_http_timeout_seconds: int = 30

    @property
    def layer_urls(self) -> dict[str, str]:
        from app.layers import database_url_for

        return {
            "dev": self.database_url,
            "preprod": self.database_url_preprod
            or database_url_for(self.database_url, "preprod"),
            "prod": self.database_url_prod or database_url_for(self.database_url, "prod"),
        }

    @property
    def cors_origins(self) -> list[str]:
        return [value.strip() for value in self.api_cors_origins.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
