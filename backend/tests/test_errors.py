from typing import Any

from ayda.core.config import Settings
from ayda.core.errors import init_error_tracking, scrub


def test_scrub_removes_personal_data() -> None:
    event: dict[str, Any] = {
        "user": {"id": "42", "username": "alex"},
        "extra": {"body": "whatever"},
        "request": {
            "method": "POST",
            "url": "https://ayda.app/api/v1/days?lat=54.71&lon=20.51",
            "headers": {"Authorization": "Bearer abc.def.ghi"},
            "cookies": "session=1",
            "data": '{"text": "к врачу в 10"}',
            "query_string": "lat=54.71",
        },
        "logentry": {"message": "bad body %s", "params": ['{"text": "секрет"}']},
        "exception": {
            "values": [
                {
                    "type": "ValueError",
                    "value": 'invalid {"text": "к врачу в 10", "lat": 54.71}',
                    "stacktrace": {"frames": [{"function": "f", "vars": {"text": "секрет"}}]},
                }
            ]
        },
        "breadcrumbs": {
            "values": [{"message": "GET /x?auth_date=1&hash=abc", "data": {"url": "/x?hash=abc"}}]
        },
    }

    out = scrub(event)

    assert "user" not in out and "extra" not in out
    assert out["request"] == {"method": "POST", "url": "https://ayda.app/api/v1/days"}
    assert "params" not in out["logentry"]
    value = out["exception"]["values"][0]["value"]
    assert "врачу" not in value and "54.71" not in value
    assert "vars" not in out["exception"]["values"][0]["stacktrace"]["frames"][0]
    crumb = out["breadcrumbs"]["values"][0]
    assert "abc" not in crumb["message"] and "data" not in crumb


def test_error_tracking_is_off_without_a_dsn(settings: Settings) -> None:
    assert not init_error_tracking(settings, "api")
