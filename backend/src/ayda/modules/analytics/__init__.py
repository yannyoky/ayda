"""Append-only log of product events (`analytics.events`), written from day one.

Public interface: `record`, `count_since` and `EventType`.
Payloads carry ids, enums and numbers only.
"""

from ayda.modules.analytics.service import (
    EventType,
    PayloadError,
    anonymize_user,
    count_since,
    record,
)

__all__ = ["EventType", "PayloadError", "anonymize_user", "count_since", "record"]
