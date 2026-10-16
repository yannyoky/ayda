"""Error tracking in the self-hosted GlitchTip through the Sentry SDK (off without SENTRY_DSN).

Events carry no personal data: no request bodies, headers, cookies, query strings or user,
no local variables, and every message and exception text passes through the same redaction
as the logs.
"""

from typing import Any, cast

import sentry_sdk

from ayda.core.config import Settings
from ayda.core.logging import redact

_REQUEST_KEEP = ("method", "url")


def _redact_value(value: Any) -> Any:
    return redact(value) if isinstance(value, str) else value


def _dict(value: Any) -> dict[str, Any] | None:
    return cast(dict[str, Any], value) if isinstance(value, dict) else None


def _values(container: Any, key: str = "values") -> list[dict[str, Any]]:
    """The dict items of `container[key]` (Sentry's `{"values": [...]}` lists)."""
    parent = _dict(container)
    items = parent.get(key) if parent else None
    if not isinstance(items, list):
        return []
    return [d for d in (_dict(i) for i in cast(list[Any], items)) if d is not None]


def scrub(event: Any, hint: Any = None) -> Any:
    """`before_send`: drop what can identify a user and redact the free text that remains."""
    ev = _dict(event)
    if ev is None:
        return event
    ev.pop("user", None)
    ev.pop("extra", None)
    request = _dict(ev.get("request"))
    if request is not None:
        kept = {k: v for k, v in request.items() if k in _REQUEST_KEEP}
        url = kept.get("url")
        if isinstance(url, str):
            kept["url"] = url.split("?", 1)[0]
        ev["request"] = kept
    if "message" in ev:
        ev["message"] = _redact_value(ev["message"])
    logentry = _dict(ev.get("logentry"))
    if logentry is not None:
        logentry.pop("params", None)
        for key in ("message", "formatted"):
            if key in logentry:
                logentry[key] = _redact_value(logentry[key])
    for exc in _values(ev.get("exception")):
        exc["value"] = _redact_value(exc.get("value"))
        for frame in _values(exc.get("stacktrace"), "frames"):
            frame.pop("vars", None)
    for crumb in _values(ev.get("breadcrumbs")):
        crumb["message"] = _redact_value(crumb.get("message"))
        crumb.pop("data", None)
    return ev


def init_error_tracking(settings: Settings, component: str) -> bool:
    if settings.sentry_dsn is None:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.environment,
        release=settings.app_release,
        server_name=component,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        traces_sample_rate=0,
        before_send=scrub,
    )
    sentry_sdk.set_tag("component", component)
    return True
