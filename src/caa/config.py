"""Settings loaded from environment variables only. No secrets live here."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Case Assessment Assistant"
    environment: str = "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
