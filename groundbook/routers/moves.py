"""Move a booking to a new interval on the same ground."""
from fastapi import APIRouter

from ..errors import AlreadyStarted, BadInterval, Cancelled, NoSuchBooking, Overlap
from ..handlers import responses
from ..schemas import MoveIn, MoveOut
from ..services import moves
from ..services.grounds import get_venue
from ..services.seed import VENUE
from . import ClockDep, SessionDep

router = APIRouter(prefix="/bookings", tags=["moves"])


@router.post(
    "/{booking_id}/move", response_model=MoveOut, summary="Move a booking: the whole new interval, buffers included, is re-checked in one transaction",
    responses={**responses((Overlap, "Moved, BK0412 would hold ground A 2026-10-03T14:20:00Z to 2026-10-03T18:30:00Z; that overlaps BK0413",
                            {"clashes_with": [{"booking_id": "BK0413", "ground_held_from": "2026-10-03T17:20:00Z", "ground_held_to": "2026-10-03T20:30:00Z"}]}),
                           (BadInterval, "`to` must be after `from`"),
                           (AlreadyStarted, "BK0412 began at 2026-10-03T14:00:00Z; it can no longer be moved"),
                           (Cancelled, "BK0412 was cancelled; request a new booking"),
                           (NoSuchBooking, "There is no booking 'BK9999' at deccan"))},
)
def move(booking_id: str, body: MoveIn, session: SessionDep, clock: ClockDep) -> MoveOut:
    venue = get_venue(session, VENUE[0])
    p = moves.move(session, venue, booking_id, body.from_at, body.to_at, clock)
    return MoveOut(booking_id=booking_id, from_at=p.booking.from_at, to_at=p.booking.to_at, ground_held_from=p.held_from, ground_held_to=p.held_to,
                   moved_at=p.booking.moved_at)