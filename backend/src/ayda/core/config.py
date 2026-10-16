import secrets
from functools import lru_cache
from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings, read only from environment variables (see `.env.example`)."""

    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    environment: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "postgresql+asyncpg://ayda:ayda@localhost:5432/ayda"
    database_echo: bool = False

    # Telegram bot (created with @BotFather); also signs Mini App initData.
    telegram_bot_token: SecretStr | None = None
    telegram_bot_username: str = "ayda_quest_bot"
    # Signs API access tokens. Required in prod; dev and test get a random one per process.
    auth_token_secret: SecretStr | None = None

    # LLM providers in fallback order, comma-separated presets from
    # ayda.modules.assistant.providers.PRESETS, optionally `preset=model`. Empty: no LLM,
    # the assistant falls back to code.
    llm_providers: str = ""
    llm_timeout_s: float = 8.0
    groq_api_key: SecretStr | None = None
    cf_account_id: SecretStr | None = None
    cf_api_token: SecretStr | None = None
    zai_api_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None
    ollama_url: str = "http://localhost:11434/v1"

    @model_validator(mode="after")
    def _secrets(self) -> Self:
        if self.auth_token_secret is None:
            if self.environment == "prod":
                raise ValueError("AUTH_TOKEN_SECRET is required in prod")
            object.__setattr__(self, "auth_token_secret", SecretStr(secrets.token_urlsafe(32)))
        if self.environment == "prod" and self.telegram_bot_token is None:
            raise ValueError("TELEGRAM_BOT_TOKEN is required in prod")
        return self

    @property
    def token_secret(self) -> str:
        assert self.auth_token_secret is not None
        return self.auth_token_secret.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()


__all__ = ["SecretStr", "Settings", "get_settings"]
