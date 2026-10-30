"""Move a booking to a new interval on the same ground."""
from fastapi import APIRouter

from ..schemas import MoveIn, MoveOut
from ..services import moves
from ..services.grounds import get_venue
from ..services.seed import VENUE
from . import ClockDep, SessionDep

router = APIRouter(prefix="/bookings")


@router.post(
    "/{booking_id}/move", response_model=MoveOut,
)
def move(booking_id: str, body: MoveIn, session: SessionDep, clock: ClockDep) -> MoveOut:
    venue = get_venue(session, VENUE[0])
    p = moves.move(session, venue, booking_id, body.from_at, body.to_at, clock)
    return MoveOut(booking_id=booking_id, from_at=p.booking.from_at, to_at=p.booking.to_at, ground_held_from=p.held_from, ground_held_to=p.held_to,
                   moved_at=p.booking.moved_at)