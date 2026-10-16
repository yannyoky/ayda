"""Append-only log of product events (`analytics.events`), written from day one.

Public interface: `record` and `EventType`. Payloads carry ids, enums and numbers only.
"""

from ayda.modules.analytics.service import EventType, PayloadError, record

__all__ = ["EventType", "PayloadError", "record"]
