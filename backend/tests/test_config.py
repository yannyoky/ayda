import pytest

from ayda.core.config import Settings
from ayda.core.push import LogPushSender
from ayda.worker import default_push_sender


def test_empty_optional_settings_are_off(monkeypatch: pytest.MonkeyPatch) -> None:
    # The prod .env template has `KEY=` lines for features that are off.
    for key in ("FCM_SERVICE_ACCOUNT_JSON", "TIMEPAD_TOKEN", "SMTP_HOST", "SENTRY_DSN"):
        monkeypatch.setenv(key, "")
    settings = Settings(environment="test")
    assert settings.fcm_service_account_json is None
    assert settings.timepad_token is None
    assert settings.smtp_host is None
    assert settings.sentry_dsn is None
    assert isinstance(default_push_sender(settings), LogPushSender)


def test_empty_value_keeps_a_non_optional_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # An empty list of sources still means "no sources", as documented.
    monkeypatch.setenv("EVENTS_SOURCES", "")
    assert Settings(environment="test").events_sources == ""
