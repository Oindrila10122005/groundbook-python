"""Request, confirm and cancel, the clash predicate on shadows.
Every transition is one session transaction."""
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clock import Clock, as_utc
from ..errors import (
    AlreadyCancelled,
    AlreadyConfirmed,
    AlreadyOver,
    AlreadyStarted,
    Cancelled,
    NoSuchBooking,
    Overlap,
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


def is_live(booking: Booking, now: datetime) -> bool:
    """Live = requested and not past hold_until, or confirmed. Cancelled and expired rows hold nothing."""
    if booking.state == "confirmed":
        return True
    return booking.state == "requested" and as_utc(booking.hold_until) > now


def clashes(session: Session, ground: Ground, held_from: datetime, held_to: datetime, now: datetime,
            exclude_id: int | None = None) -> list[tuple[Booking, datetime, datetime]]:
    """The clash predicate, on shadows, half-open: `held_from_new < held_to_other AND held_from_other < held_to_new`.
    The request and the confirm call this one function; `exclude_id` is the booking itself."""
    window_start, window_end = held_from - timedelta(days=1), held_to + timedelta(days=1)
    rows = session.execute(select(Booking, EventType).join(EventType, Booking.event_type_id == EventType.id)
                           .where(Booking.ground_id == ground.id, Booking.from_at >= window_start, Booking.from_at < window_end)
                           .order_by(Booking.from_at, Booking.id)).all()
    out = []
    for other, other_type in rows:
        if other.id == exclude_id or not is_live(other, now):
            continue
        other_from, other_to = shadow(other.from_at, other.to_at, other_type)
        if held_from < other_to and other_from < held_to:
            out.append((other, other_from, other_to))
    return out


def clash_fields(found: list[tuple[Booking, datetime, datetime]]) -> list[dict]:
    return [{"booking_id": booking_public(b.id), "ground_held_from": _z(f), "ground_held_to": _z(t)} for b, f, t in found]


def _z(dt: datetime) -> str:
    return as_utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")


def request(session: Session, venue: Venue, ground_code: str, event_code: str, from_at: datetime, to_at: datetime, club: str,
            clock: Clock, settings: Settings) -> Placed:
    """404 ground, 400 event type, 400 bad-interval, 409 overlap; else a requested booking with its hold."""
    ground = get_ground(session, venue, ground_code)
    event_type = get_event_type(session, venue, event_code)
    now = clock.now()
    held_from, held_to = check_interval(ground, event_type, from_at, to_at, now)
    found = clashes(session, ground, held_from, held_to, now)
    if found:
        raise Overlap(f"Ground {ground.code} is held {_z(held_from)} to {_z(held_to)} for this {event_type.code}; "
                      f"that overlaps {', '.join(booking_public(b.id) for b, _, _ in found)}", clashes_with=clash_fields(found))
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
    """Requested and now < from. Cancelled is its own refusal, and the clash check runs again."""
    booking = get_booking(session, venue, public_id)
    now = clock.now()
    if booking.state == "cancelled":
        raise Cancelled(f"{public_id} was cancelled; request a new booking")
    if booking.state == "confirmed":
        raise AlreadyConfirmed(f"{public_id} was confirmed at {_z(booking.confirmed_at)}")
    if now >= as_utc(booking.from_at):
        raise AlreadyStarted(f"{public_id} began at {_z(booking.from_at)}; it can no longer be confirmed")
    p = placed(session, booking)
    found = clashes(session, p.ground, p.held_from, p.held_to, now, exclude_id=booking.id)
    if found:
        raise Overlap(f"Since {public_id} was requested, {', '.join(booking_public(b.id) for b, _, _ in found)} took the ground "
                      f"{_z(p.held_from)} to {_z(p.held_to)}", clashes_with=clash_fields(found))
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