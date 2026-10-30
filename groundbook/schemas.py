"""Request and response models. Every response goes through one of these; bodies use Field constraints."""

from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, model_validator

BookingState = Literal["requested", "confirmed", "cancelled", "expired"]
MIN_INTERVAL = timedelta(minutes=30)
MAX_INTERVAL = timedelta(hours=12)


def _iso_z(dt: datetime) -> str:
    """SQLite hands naive datetimes back; everything the app stores is UTC, so a naive value is UTC, never local time."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


UtcZ = Annotated[datetime, PlainSerializer(_iso_z, return_type=str)]


class Interval(BaseModel):
    """What a body must satisfy to be *valid* -- the impossible (to <= from, the past, outside hours) is the
    service's 400, not a 422. The length bounds are validation because they are true of any request whatever the day.
    A body names the interval `from`/`to` only; the Python names are not accepted on the wire."""
    from_at: datetime = Field(alias="from")
    to_at: datetime = Field(alias="to")

    @model_validator(mode="after")
    def _length(self):
        if self.to_at > self.from_at:
            length = self.to_at - self.from_at
            if length < MIN_INTERVAL:
                raise ValueError("the interval must be at least 30 minutes")
            if length > MAX_INTERVAL:
                raise ValueError("the interval must be at most 12 hours")
        return self


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



class BookingIn(Interval):
    ground: str = Field(min_length=1, max_length=8)
    event: str = Field(min_length=1, max_length=24)
    club: str = Field(min_length=2, max_length=80)


class BookingCreatedOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    booking_id: str
    ground: str
    event: str
    from_at: UtcZ = Field(serialization_alias="from")
    to_at: UtcZ = Field(serialization_alias="to")
    ground_held_from: UtcZ
    ground_held_to: UtcZ
    state: BookingState
    hold_until: UtcZ


class BookingOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    booking_id: str
    ground: str
    event: str
    from_at: UtcZ = Field(serialization_alias="from")
    to_at: UtcZ = Field(serialization_alias="to")
    ground_held_from: UtcZ
    ground_held_to: UtcZ
    state: BookingState

class ConfirmOut(BaseModel):
    booking_id: str
    state: BookingState
    confirmed_at: UtcZ


class CancelOut(BaseModel):
    booking_id: str
    state: BookingState
    cancelled_at: UtcZ
    late: bool