"""Request and read, confirm and cancel. Routes parse, delegate to the service and shape the answer."""
from fastapi import APIRouter, Response

from ..schemas import BookingCreatedOut, BookingIn, BookingOut, CancelOut, ConfirmOut
from ..services import bookings
from ..services.grounds import get_venue
from ..services.seed import VENUE
from . import ClockDep, SessionDep, SettingsDep

router = APIRouter(prefix="/bookings")


@router.post(
    "",
    response_model=BookingCreatedOut, status_code=201,
)
def request_booking(body: BookingIn, response: Response, session: SessionDep, clock: ClockDep, settings: SettingsDep) -> BookingCreatedOut:
    venue = get_venue(session, VENUE[0])
    p = bookings.request(session, venue, body.ground, body.event, body.from_at, body.to_at, body.club, clock, settings)
    response.headers["Location"] = f"/bookings/{bookings.public(p.booking)}"
    return BookingCreatedOut(booking_id=bookings.public(p.booking), ground=p.ground.code, event=p.event_type.code, from_at=p.booking.from_at,
                             to_at=p.booking.to_at, ground_held_from=p.held_from, ground_held_to=p.held_to, state=p.booking.state,
                             hold_until=p.booking.hold_until)


@router.get("/{booking_id}", response_model=BookingOut, response_model_exclude_none=True)
def read_booking(booking_id: str, session: SessionDep) -> BookingOut:
    venue = get_venue(session, VENUE[0])
    booking = bookings.get_booking(session, venue, booking_id)
    p = bookings.placed(session, booking)
    return BookingOut(booking_id=booking_id, ground=p.ground.code, event=p.event_type.code, from_at=booking.from_at, to_at=booking.to_at,
                      ground_held_from=p.held_from, ground_held_to=p.held_to, state=booking.state, events=bookings.timeline(session, booking))


@router.post(
    "/{booking_id}/confirm", response_model=ConfirmOut,
)
def confirm(booking_id: str, session: SessionDep, clock: ClockDep) -> ConfirmOut:
    venue = get_venue(session, VENUE[0])
    booking = bookings.confirm(session, venue, booking_id, clock)
    return ConfirmOut(booking_id=booking_id, state=booking.state, confirmed_at=booking.confirmed_at)


@router.post(
    "/{booking_id}/cancel", response_model=CancelOut,
)
def cancel(booking_id: str, session: SessionDep, clock: ClockDep) -> CancelOut:
    venue = get_venue(session, VENUE[0])
    booking = bookings.cancel(session, venue, booking_id, clock)
    return CancelOut(booking_id=booking_id, state=booking.state, cancelled_at=booking.cancelled_at, late=booking.late_cancel)