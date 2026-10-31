from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from ..errors import NoSuchGround, NoSuchVenue
from ..handlers import FILTER_RESPONSE, responses
from ..ids import booking_public
from ..schemas import (
    DayBookingOut,
    DayOut,
    EventTypeOut,
    EventTypesOut,
    GroundOut,
    GroundsOut,
)
from ..services import grounds
from . import ClockDep, SessionDep

router = APIRouter(prefix="/venues/{venue}", tags=["grounds"])
NO_VENUE = responses((NoSuchVenue, "There is no venue 'mumbai'"))


@router.get("/grounds", response_model=GroundsOut, summary="The grounds and their opening hours (Sunday has its own)", responses=NO_VENUE)
def list_grounds(venue: str, session: SessionDep) -> GroundsOut:
    v = grounds.get_venue(session, venue)
    return GroundsOut(venue=v.slug, grounds=[GroundOut(ground=g.code, name=g.name, opens=g.opens, closes=g.closes, sunday_opens=g.sunday_opens,
                                                       sunday_closes=g.sunday_closes) for g in grounds.list_grounds(session, v)])


@router.get("/event-types", response_model=EventTypesOut, summary="The event types with their setup and teardown buffers", responses=NO_VENUE)
def list_event_types(venue: str, session: SessionDep) -> EventTypesOut:
    v = grounds.get_venue(session, venue)
    return EventTypesOut(event_types=[EventTypeOut(code=t.code, name=t.name, setup_minutes=t.setup_minutes, teardown_minutes=t.teardown_minutes)
                                      for t in grounds.list_event_types(session, v)])


@router.get(
    "/grounds/{ground}/day",
    response_model=DayOut, summary="One ground's day: bookings in `from` order, each with the ground held around it",
    responses={**responses((NoSuchGround, "There is no ground 'Z' at deccan"), (NoSuchVenue, "There is no venue 'mumbai'")), **FILTER_RESPONSE},
)
def read_day(venue: str, ground: str, session: SessionDep, clock: ClockDep,
             date_: Annotated[date | None, Query(alias="date", description="YYYY-MM-DD; today when omitted")] = None) -> DayOut:
    v = grounds.get_venue(session, venue)
    g = grounds.get_ground(session, v, ground)
    on = date_ or clock.now().date()
    opens, closes = grounds.hours_for(g, on)
    blocks = grounds.day(session, g, on)
    return DayOut(venue=v.slug, ground=g.code, date=on, opens=opens, closes=closes,
                  bookings=[DayBookingOut(booking_id=booking_public(b.booking.id), event=b.event_type.code, from_at=b.booking.from_at,
                                          to_at=b.booking.to_at, ground_held_from=b.held_from, ground_held_to=b.held_to, state=b.booking.state)
                            for b in blocks])