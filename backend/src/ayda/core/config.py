import re
import secrets
from datetime import time
from functools import lru_cache
from typing import Any, Literal, Self

from pydantic import SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Telegram's secret_token alphabet; at least 16 characters so it cannot be guessed.
_WEBHOOK_SECRET = re.compile(r"[A-Za-z0-9_-]{16,256}")


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
    # Public origin of the app, e.g. https://ayda.example.ru. With it invite links are
    # <origin>/i/<code> (they open the native app; Caddy sends the rest to the bot).
    invite_base_url: str | None = None
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
    # Keys for the backup bucket when the provider issues a key pair per bucket (Beget);
    # unset: the S3 keys above.
    backup_s3_access_key_id: SecretStr | None = None
    backup_s3_secret_access_key: SecretStr | None = None
    backup_keep_days: int = 14
    backup_at: time = time(3, 30)
    backup_timezone: str = "Europe/Moscow"

    # Local events (ADR 0008): sources in order, comma-separated (`timepad`, `kudago`); empty:
    # no events. Loaded once a day after `events_ingest_at` local time for the next 3 days.
    events_sources: str = "timepad,kudago"
    events_ingest_at: time = time(4, 0)
    events_timezone: str = "Europe/Moscow"
    # Optional: a Timepad API token only raises the rate limit; public events need none.
    timepad_token: SecretStr | None = None
    # Venues for meetups (ADR 0011): public Overpass instances in order, comma-separated;
    # empty: no venues. A city with users is queried about once a month, a few per night.
    # The Russian mirror first, since prod runs on a Russian VPS; the main instance is the fallback.
    venues_overpass_urls: str = (
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter,"
        "https://overpass-api.de/api/interpreter"
    )
    venues_radius_m: int = 7000

    # Realtime through Centrifugo (ADR 0007). Without the API key nothing is published;
    # without the token secret the Mini App gets no realtime token and polls REST instead.
    centrifugo_api_url: str = "http://localhost:8001/api"
    centrifugo_public_url: str = "ws://localhost:8001/connection/websocket"
    centrifugo_api_key: SecretStr | None = None
    centrifugo_token_secret: SecretStr | None = None

    # Email for sign-in codes in the native apps (ADR 0009), e.g. Yandex 360 or Unisender Go.
    # Without a host, email sign-in answers 503 and Telegram stays the only way in.
    smtp_host: str | None = None
    smtp_port: int = 465
    smtp_security: Literal["ssl", "starttls", "none"] = "ssl"
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str = "Ayda <noreply@ayda.example>"

    # Push notifications for the native apps through FCM HTTP v1 (ADR 0009): the whole
    # service-account JSON of the Firebase project. Empty: pushes are only logged.
    fcm_service_account_json: SecretStr | None = None

    # Error tracking: a Sentry-compatible DSN of the self-hosted GlitchTip; empty: off.
    sentry_dsn: SecretStr | None = None
    # Set by the image build (git sha), so errors are grouped by release.
    app_release: str | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _empty_is_unset(cls, value: Any, info: ValidationInfo) -> Any:
        """`KEY=` in .env means "off" for an optional setting, not an empty key: an empty
        FCM_SERVICE_ACCOUNT_JSON used to crash the worker on startup."""
        if value == "" and info.field_name and cls.model_fields[info.field_name].default is None:
            return None
        return value

    @model_validator(mode="after")
    def _secrets(self) -> Self:
        if self.auth_token_secret is None:
            if self.environment == "prod":
                raise ValueError("AUTH_TOKEN_SECRET is required in prod")
            object.__setattr__(self, "auth_token_secret", SecretStr(secrets.token_urlsafe(32)))
        if self.environment == "prod":
            for name in ("telegram_bot_token", "centrifugo_api_key", "centrifugo_token_secret"):
                if getattr(self, name) is None:
                    raise ValueError(f"{name.upper()} is required in prod")
        if self.telegram_webhook_url:
            # Without the secret anyone could post a fake "confirm sign-in" tap (audit V1).
            secret = self.telegram_webhook_secret
            if secret is None or not _WEBHOOK_SECRET.fullmatch(secret.get_secret_value()):
                raise ValueError(
                    "TELEGRAM_WEBHOOK_SECRET is required with TELEGRAM_WEBHOOK_URL: "
                    "16-256 characters A-Z, a-z, 0-9, _ or -"
                )
        return self

    @property
    def token_secret(self) -> str:
        assert self.auth_token_secret is not None
        return self.auth_token_secret.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()


__all__ = ["SecretStr", "Settings", "get_settings"]
