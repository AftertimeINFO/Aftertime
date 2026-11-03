from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Aftertime Platform"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://aftertime:aftertime-local@postgres:5432/aftertime"
    redis_url: str = "redis://redis:6379/0"
    api_cors_origins: str = "http://localhost:8080,http://localhost:8083,http://localhost:5173"
    sync_poll_seconds: int = 5
    sync_http_timeout_seconds: int = 30

    @property
    def cors_origins(self) -> list[str]:
        return [value.strip() for value in self.api_cors_origins.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
