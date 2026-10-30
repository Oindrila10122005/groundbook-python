"""Public ids are opaque strings (booking BK0412, ground A, event type league); database integers never reach the wire."""
import re

_BOOKING = re.compile(r"^BK(\d{4,})$")


def booking_public(internal_id: int) -> str:
    return f"BK{internal_id:04d}"


def booking_internal(public_id: str) -> int | None:
    m = _BOOKING.match(public_id or "")
    return int(m.group(1)) if m else None