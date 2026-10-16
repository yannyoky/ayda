import secrets
from datetime import time
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
    # Mini App URL for the bot's buttons; without it the buttons use t.me/<bot>?startapp.
    miniapp_url: str | None = None
    # Production: Telegram calls this URL (proxied to the bot process); empty: polling.
    telegram_webhook_url: str | None = None
    telegram_webhook_secret: SecretStr | None = None
    bot_port: int = 8081
    # Signs API access tokens. Required in prod; dev and test get a random one per process.
    auth_token_secret: SecretStr | None = None

    # LLM providers in fallback order, comma-separated presets from
    # ayda.modules.assistant.providers.PRESETS, optionally `preset=model`; ADR 0005 chain:
    # groq-gptoss20b,groq-gptoss120b,cloudflare-llama70b. Empty: no LLM, code-only pools.
    llm_providers: str = ""
    llm_timeout_s: float = 8.0
    groq_api_key: SecretStr | None = None
    cf_account_id: SecretStr | None = None
    cf_api_token: SecretStr | None = None
    ollama_url: str = "http://localhost:11434/v1"

    # S3-compatible storage in Russia for photos (MinIO locally). The bucket is private:
    # uploads and reads go through short-lived presigned URLs.
    s3_endpoint_url: str = "http://localhost:9000"
    s3_public_endpoint_url: str | None = None
    s3_region: str = "ru-central1"
    s3_bucket: str = "ayda-media"
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None

    # Daily PostgreSQL backup (pg_dump) to a private bucket of the same S3 provider in Russia.
    backup_bucket: str = "ayda-backups"
    backup_keep_days: int = 14
    backup_at: time = time(3, 30)
    backup_timezone: str = "Europe/Moscow"

    # Error tracking: a Sentry-compatible DSN of the self-hosted GlitchTip; empty: off.
    sentry_dsn: SecretStr | None = None
    # Set by the image build (git sha), so errors are grouped by release.
    app_release: str | None = None

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
