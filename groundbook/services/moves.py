"""Moves a booking to a new interval."""
from datetime import datetime

from sqlalchemy.orm import Session

from ..clock import Clock, as_utc
from ..errors import AlreadyStarted, Cancelled, Overlap
from ..ids import booking_public
from ..models import Venue
from .bookings import Placed, _z, clash_fields, clashes, get_booking, placed
from .grounds import check_interval


def move(session: Session, venue: Venue, public_id: str, from_at: datetime, to_at: datetime, clock: Clock) -> Placed:
    booking = get_booking(session, venue, public_id)
    now = clock.now()
    if booking.state == "cancelled":
        raise Cancelled(f"{public_id} was cancelled; request a new booking")
    if now >= as_utc(booking.from_at):
        raise AlreadyStarted(f"{public_id} began at {_z(booking.from_at)}; it can no longer be moved")
    p = placed(session, booking)
    held_from, held_to = check_interval(p.ground, p.event_type, from_at, to_at, now)
    found = clashes(session, p.ground, held_from, held_to, now, exclude_id=booking.id)
    if found:
        raise Overlap(f"Moved, {public_id} would hold ground {p.ground.code} {_z(held_from)} to {_z(held_to)}; that overlaps "
                      f"{', '.join(booking_public(b.id) for b, _, _ in found)}", clashes_with=clash_fields(found))
    previous_from, previous_to = as_utc(booking.from_at), as_utc(booking.to_at)
    booking.previous_from, booking.previous_to = previous_from, previous_to
    booking.from_at, booking.to_at = as_utc(from_at), as_utc(to_at)
    booking.moved_at = now
    session.flush()                                                     # one UPDATE: the old interval released, the new one taken
    session.commit()
    return Placed(booking, p.ground, p.event_type, held_from, held_to)