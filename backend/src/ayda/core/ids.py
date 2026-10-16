import os
import time
import uuid


def uuid7() -> uuid.UUID:
    """A time-ordered UUID v7 (RFC 9562): 48-bit Unix ms timestamp, then random bits."""
    ts_ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")
    value = (ts_ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76  # version
    value |= ((rand >> 62) & 0xFFF) << 64  # rand_a, 12 bits
    value |= 0b10 << 62  # variant
    value |= rand & ((1 << 62) - 1)  # rand_b, 62 bits
    return uuid.UUID(int=value)
