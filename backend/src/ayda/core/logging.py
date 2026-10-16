"""Logging setup with a redaction filter: no initData, tokens, free text or coordinates in
logs, whatever a library or a careless log line passes in."""

import logging
import re

REDACTED = "[redacted]"

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Telegram initData (raw or URL-encoded) and its parts
    (re.compile(r"(query_id|auth_date|hash|signature|user)=[^&\s\"']+"), rf"\1={REDACTED}"),
    (re.compile(r"(\"?init_?data\"?\s*[:=]\s*)\"[^\"]*\"", re.I), rf'\1"{REDACTED}"'),
    # Bearer tokens, JWTs, Telegram bot tokens, presigned URL signatures
    (re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.I), f"Bearer {REDACTED}"),
    (re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"), REDACTED),
    (re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b"), REDACTED),
    (re.compile(r"(X-Amz-(?:Signature|Credential)=)[^&\s\"']+"), rf"\1{REDACTED}"),
    # Coordinates in query strings and JSON
    (re.compile(r"\b(lat|lon|lng|latitude|longitude)=[-+]?\d+(\.\d+)?", re.I), rf"\1={REDACTED}"),
    (
        re.compile(r"(\"(?:lat|lon|lng|latitude|longitude)\"\s*:\s*)[-+]?\d+(\.\d+)?", re.I),
        rf"\1{REDACTED}",
    ),
    # Free text fields in JSON bodies and dict reprs
    (
        re.compile(
            r"""(["'](?:text|caption|comment|title|first_name|last_name|username)["']\s*:\s*)"""
            r"""(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')"""
        ),
        rf'\1"{REDACTED}"',
    ),
)


def redact(message: str) -> str:
    for pattern, replacement in _PATTERNS:
        message = pattern.sub(replacement, message)
    return message


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except (TypeError, ValueError):
            message = str(record.msg)
        record.msg = redact(message)
        record.args = None
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        return True


def configure_logging(level: int = logging.INFO) -> None:
    """Root handler with the filter; uvicorn's loggers propagate to it."""
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "aiogram", "httpx"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
