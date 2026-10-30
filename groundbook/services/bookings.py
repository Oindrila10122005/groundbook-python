"""Request, confirm and cancel.
Every transition is one session transaction."""
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..clock import Clock, as_utc
from ..errors import (
    AlreadyCancelled,
    AlreadyConfirmed,
    AlreadyOver,
    AlreadyStarted,
    Cancelled,
    NoSuchBooking,
)
from ..ids import booking_internal, booking_public
from ..models import Booking, EventType, Ground, Venue
from ..settings import Settings
from .grounds import check_interval, get_event_type, get_ground, shadow


@dataclass
class Placed:
    booking: Booking
    ground: Ground
    event_type: EventType
    held_from: datetime
    held_to: datetime


def public(booking: Booking) -> str:
    return booking_public(booking.id)


def get_booking(session: Session, venue: Venue, public_id: str) -> Booking:
    internal = booking_internal(public_id)
    booking = session.get(Booking, internal) if internal is not None else None
    if booking is None or booking.venue_id != venue.id:
        raise NoSuchBooking(f"There is no booking '{public_id}' at {venue.slug}")
    return booking


def _z(dt: datetime) -> str:
    return as_utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")


def request(session: Session, venue: Venue, ground_code: str, event_code: str, from_at: datetime, to_at: datetime, club: str,
            clock: Clock, settings: Settings) -> Placed:
    """404 ground, 400 event type, 400 bad-interval; else a requested booking with its hold."""
    ground = get_ground(session, venue, ground_code)
    event_type = get_event_type(session, venue, event_code)
    now = clock.now()
    held_from, held_to = check_interval(ground, event_type, from_at, to_at, now)
    booking = Booking(venue_id=venue.id, ground_id=ground.id, event_type_id=event_type.id, club_name=club, from_at=as_utc(from_at),
                      to_at=as_utc(to_at), state="requested", requested_at=now, hold_until=now + timedelta(hours=settings.hold_hours))
    session.add(booking)
    session.commit()
    return Placed(booking, ground, event_type, held_from, held_to)


def placed(session: Session, booking: Booking) -> Placed:
    ground = session.get(Ground, booking.ground_id)
    event_type = session.get(EventType, booking.event_type_id)
    return Placed(booking, ground, event_type, *shadow(booking.from_at, booking.to_at, event_type))


def confirm(session: Session, venue: Venue, public_id: str, clock: Clock) -> Booking:
    """Requested and now < from; a cancelled booking is its own refusal."""
    booking = get_booking(session, venue, public_id)
    now = clock.now()
    if booking.state == "cancelled":
        raise Cancelled(f"{public_id} was cancelled; request a new booking")
    if booking.state == "confirmed":
        raise AlreadyConfirmed(f"{public_id} was confirmed at {_z(booking.confirmed_at)}")
    if now >= as_utc(booking.from_at):
        raise AlreadyStarted(f"{public_id} began at {_z(booking.from_at)}; it can no longer be confirmed")
    booking.state = "confirmed"
    booking.confirmed_at = now
    session.commit()
    return booking


def cancel(session: Session, venue: Venue, public_id: str, clock: Clock) -> Booking:
    """Requested or confirmed and now < to; from `from` onwards it is a late cancel, allowed and flagged."""
    booking = get_booking(session, venue, public_id)
    now = clock.now()
    if booking.state == "cancelled":
        raise AlreadyCancelled(f"{public_id} was cancelled at {_z(booking.cancelled_at)}")
    if now >= as_utc(booking.to_at):
        raise AlreadyOver(f"{public_id} ended at {_z(booking.to_at)}; it can no longer be cancelled")
    late = now >= as_utc(booking.from_at)
    booking.state = "cancelled"
    booking.cancelled_at = now
    booking.late_cancel = late
    session.commit()
    return booking