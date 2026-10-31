"""The venue, its grounds and event types, the hours for a weekday, and the one shadow function every other
service reuses. The shadow is computed here, on read, from the event type -- never stored."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clock import as_utc
from ..errors import BadInterval, NoSuchEventType, NoSuchGround, NoSuchVenue
from ..models import Booking, EventType, Ground, Venue


def get_venue(session: Session, slug: str) -> Venue:
    venue = session.scalar(select(Venue).where(Venue.slug == slug))
    if venue is None:
        raise NoSuchVenue(f"There is no venue '{slug}'")
    return venue


def get_ground(session: Session, venue: Venue, code: str) -> Ground:
    ground = session.scalar(select(Ground).where(Ground.venue_id == venue.id, Ground.code == code))
    if ground is None:
        raise NoSuchGround(f"There is no ground '{code}' at {venue.slug}")
    return ground


def get_event_type(session: Session, venue: Venue, code: str) -> EventType:
    event_type = session.scalar(select(EventType).where(EventType.venue_id == venue.id, EventType.code == code))
    if event_type is None:
        raise NoSuchEventType(f"There is no event type '{code}' at {venue.slug}")
    return event_type


def list_grounds(session: Session, venue: Venue) -> list[Ground]:
    return list(session.scalars(select(Ground).where(Ground.venue_id == venue.id).order_by(Ground.code)))


def list_event_types(session: Session, venue: Venue) -> list[EventType]:
    return list(session.scalars(select(EventType).where(EventType.venue_id == venue.id).order_by(EventType.id)))


def buffers(session: Session, venue: Venue) -> dict[str, tuple[int, int]]:
    """The live buffer table, per event type."""
    return {t.code: (t.setup_minutes, t.teardown_minutes) for t in list_event_types(session, venue)}


def hours_for(ground: Ground, day: date) -> tuple[str, str]:
    """Sunday uses the sunday_* columns."""
    if day.weekday() == 6:
        return ground.sunday_opens, ground.sunday_closes
    return ground.opens, ground.closes


def shadow(from_at: datetime, to_at: datetime, event_type: EventType) -> tuple[datetime, datetime]:
    """ground_held_from = from - setup, ground_held_to = to + teardown. The only place the buffers are applied."""
    return (as_utc(from_at) - timedelta(minutes=event_type.setup_minutes),
            as_utc(to_at) + timedelta(minutes=event_type.teardown_minutes))


def _at(day: date, hhmm: str) -> datetime:
    hour, minute = (int(x) for x in hhmm.split(":"))
    return datetime.combine(day, time(hour, minute), tzinfo=timezone.utc)


def check_interval(ground: Ground, event_type: EventType, from_at: datetime, to_at: datetime, now: datetime) -> tuple[datetime, datetime]:
    """A valid body that asks for something impossible is 400 bad-interval. Returns the shadow when it fits."""
    from_at, to_at = as_utc(from_at), as_utc(to_at)
    if to_at <= from_at:
        raise BadInterval("`to` must be after `from`")
    if from_at < now:
        raise BadInterval(f"`from` is before now ({now.strftime('%Y-%m-%dT%H:%M:%SZ')}); nobody books the past")
    if from_at.date() != to_at.date():
        raise BadInterval("`from` and `to` must be on the same date")
    opens, closes = hours_for(ground, from_at.date())
    held_from, held_to = shadow(from_at, to_at, event_type)
    if held_from < _at(from_at.date(), opens) or held_to > _at(from_at.date(), closes):
        raise BadInterval(f"With {event_type.setup_minutes} min setup and {event_type.teardown_minutes} min teardown the ground is held "
                          f"{held_from.strftime('%H:%M')}-{held_to.strftime('%H:%M')}; ground {ground.code} opens at {opens} and closes at {closes} "
                          f"on {from_at.strftime('%A')}", opens=opens, closes=closes)
    return held_from, held_to


@dataclass
class Block:
    booking: Booking
    event_type: EventType
    held_from: datetime
    held_to: datetime


def day(session: Session, ground: Ground, on: date) -> list[Block]:
    """One ground's day as blocks in `from` order, each with its derived shadow (every state; the strip colours them)."""
    start, end = _at(on, "00:00"), _at(on, "00:00") + timedelta(days=1)
    rows = session.execute(select(Booking, EventType).join(EventType, Booking.event_type_id == EventType.id)
                           .where(Booking.ground_id == ground.id, Booking.from_at >= start, Booking.from_at < end)
                           .order_by(Booking.from_at, Booking.id)).all()
    return [Block(b, t, *shadow(b.from_at, b.to_at, t)) for b, t in rows]