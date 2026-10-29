"""Request and response models. Every response goes through one of these.
`from`/`to` are reserved-looking names on the wire, so the models alias them."""
"""The shape of every answer the app gives."""

from datetime import date, datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

BookingState = Literal["requested", "confirmed", "cancelled", "expired"]


def _iso_z(dt: datetime) -> str:
    """SQLite hands naive datetimes back; everything the app stores is UTC, so a naive value is UTC, never local time."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


UtcZ = Annotated[datetime, PlainSerializer(_iso_z, return_type=str)]


class GroundOut(BaseModel):
    ground: str
    name: str
    opens: str
    closes: str
    sunday_opens: str
    sunday_closes: str




class GroundsOut(BaseModel):
    venue: str
    grounds: list[GroundOut]


class EventTypeOut(BaseModel):
    code: str
    name: str
    setup_minutes: int
    teardown_minutes: int


class EventTypesOut(BaseModel):
    event_types: list[EventTypeOut]


class DayBookingOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    booking_id: str
    event: str
    from_at: UtcZ = Field(serialization_alias="from")
    to_at: UtcZ = Field(serialization_alias="to")
    ground_held_from: UtcZ
    ground_held_to: UtcZ
    state: BookingState


class DayOut(BaseModel):
    venue: str
    ground: str
    date: date
    opens: str
    closes: str
    bookings: list[DayBookingOut]