"""Request and read, confirm and cancel. Routes parse, delegate to the service and shape the answer."""
from fastapi import APIRouter, Response

from ..errors import (
    AlreadyCancelled,
    AlreadyConfirmed,
    AlreadyOver,
    AlreadyStarted,
    BadInterval,
    Cancelled,
    NoSuchBooking,
    NoSuchEventType,
    NoSuchGround,
    Overlap,
)
from ..handlers import responses
from ..schemas import BookingCreatedOut, BookingIn, BookingOut, CancelOut, ConfirmOut
from ..services import bookings
from ..services.grounds import get_venue
from ..services.seed import VENUE
from . import ClockDep, SessionDep, SettingsDep

router = APIRouter(prefix="/bookings", tags=["bookings"])
CLASH = {"clashes_with": [{"booking_id": "BK0411", "ground_held_from": "2026-10-03T13:20:00Z", "ground_held_to": "2026-10-03T16:30:00Z"}]}
NO_BOOKING = (NoSuchBooking, "There is no booking 'BK9999' at deccan")
CREATED = {201: {"description": "Requested: the slot is held until `hold_until`",
                 "headers": {"Location": {"schema": {"type": "string"}, "description": "Where to read the new booking: /bookings/{booking_id}"}}}}


@router.post(
    "",
    response_model=BookingCreatedOut, status_code=201, summary="A club asks for a ground, an interval and an event type; the slot is held",
    responses={**responses((Overlap, "Ground A is held 2026-10-03T15:20:00Z to 2026-10-03T18:30:00Z for this league; that overlaps BK0411", CLASH),
                           (BadInterval, "With 40 min setup and 30 min teardown the ground is held 05:20-08:30; ground A opens at 06:00 and closes at 22:00 on Saturday",
                            {"opens": "06:00", "closes": "22:00"}),
                           (NoSuchEventType, "There is no event type 'concert' at deccan"),
                           (NoSuchGround, "There is no ground 'Z' at deccan")), **CREATED},
)
def request_booking(body: BookingIn, response: Response, session: SessionDep, clock: ClockDep, settings: SettingsDep) -> BookingCreatedOut:
    venue = get_venue(session, VENUE[0])
    p = bookings.request(session, venue, body.ground, body.event, body.from_at, body.to_at, body.club, clock, settings)
    response.headers["Location"] = f"/bookings/{bookings.public(p.booking)}"
    return BookingCreatedOut(booking_id=bookings.public(p.booking), ground=p.ground.code, event=p.event_type.code, from_at=p.booking.from_at,
                             to_at=p.booking.to_at, ground_held_from=p.held_from, ground_held_to=p.held_to, state=p.booking.state,
                             hold_until=p.booking.hold_until)


@router.get("/{booking_id}", response_model=BookingOut, response_model_exclude_none=True, summary="One booking with the ground held around it and its timeline",
            responses=responses(NO_BOOKING))
def read_booking(booking_id: str, session: SessionDep) -> BookingOut:
    venue = get_venue(session, VENUE[0])
    booking = bookings.get_booking(session, venue, booking_id)
    p = bookings.placed(session, booking)
    return BookingOut(booking_id=booking_id, ground=p.ground.code, event=p.event_type.code, from_at=booking.from_at, to_at=booking.to_at,
                      ground_held_from=p.held_from, ground_held_to=p.held_to, state=booking.state, events=bookings.timeline(session, booking))


@router.post(
    "/{booking_id}/confirm", response_model=ConfirmOut, summary="The office confirms a requested booking (the clash check runs again)",
    responses=responses((AlreadyStarted, "BK0412 began at 2026-10-03T14:00:00Z; it can no longer be confirmed"),
                        (Cancelled, "BK0412 was cancelled; request a new booking"),
                        (AlreadyConfirmed, "BK0412 was confirmed at 2026-10-01T09:00:00Z"),
                        (Overlap, "Since BK0412 was requested, BK0413 took the ground 2026-10-03T13:20:00Z to 2026-10-03T17:30:00Z", CLASH),
                        NO_BOOKING),
)
def confirm(booking_id: str, session: SessionDep, clock: ClockDep) -> ConfirmOut:
    venue = get_venue(session, VENUE[0])
    booking = bookings.confirm(session, venue, booking_id, clock)
    return ConfirmOut(booking_id=booking_id, state=booking.state, confirmed_at=booking.confirmed_at)


@router.post(
    "/{booking_id}/cancel", response_model=CancelOut, summary="Cancel a requested or confirmed booking; after `from` it is a late cancel",
    responses=responses((AlreadyOver, "BK0412 ended at 2026-10-03T17:00:00Z; it can no longer be cancelled"),
                        (AlreadyCancelled, "BK0412 was cancelled at 2026-10-03T14:20:00Z"), NO_BOOKING),
)
def cancel(booking_id: str, session: SessionDep, clock: ClockDep) -> CancelOut:
    venue = get_venue(session, VENUE[0])
    booking = bookings.cancel(session, venue, booking_id, clock)
    return CancelOut(booking_id=booking_id, state=booking.state, cancelled_at=booking.cancelled_at, late=booking.late_cancel)