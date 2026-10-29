"""The venue, its grounds and event types, and the hours for a weekday."""
"""Finds a venue or a ground, or says no."""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import NoSuchGround, NoSuchVenue
from ..models import EventType, Ground, Venue


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




def list_grounds(session: Session, venue: Venue) -> list[Ground]:
    return list(session.scalars(select(Ground).where(Ground.venue_id == venue.id).order_by(Ground.code)))


def list_event_types(session: Session, venue: Venue) -> list[EventType]:
    return list(session.scalars(select(EventType).where(EventType.venue_id == venue.id).order_by(EventType.id)))


def hours_for(ground: Ground, day: date) -> tuple[str, str]:
    """Sunday uses the sunday_* columns."""
    if day.weekday() == 6:
        return ground.sunday_opens, ground.sunday_closes
    return ground.opens, ground.closes