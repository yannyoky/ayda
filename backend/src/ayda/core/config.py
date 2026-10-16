from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings, read only from environment variables (see `.env.example`)."""

    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    environment: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "postgresql+asyncpg://ayda:ayda@localhost:5432/ayda"
    database_echo: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


__all__ = ["SecretStr", "Settings", "get_settings"]
