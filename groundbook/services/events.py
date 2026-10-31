"""Append one event row inside the caller's transaction. Ids, intervals and facts only -- never the club's
phone or email (the app does not even collect them).

The row is written with a Core INSERT, never through an ORM object: nothing in the code holds an Event it could
change and flush, so the only path to the table is insert. The database triggers (db.py) refuse UPDATE and DELETE."""
import json
import logging
from datetime import datetime

from sqlalchemy import insert
from sqlalchemy.orm import Session

from ..ids import booking_public
from ..models import Event

log = logging.getLogger("groundbook.events")

# Requests carry no identity: every transition is done by the municipal office (Deepa takes the calls).
OFFICE = "office"


def record(session: Session, venue_id: int, booking_id: int, kind: str, at: datetime, actor_id: str,
           data: dict | None = None) -> int:
    """Insert one event and return its id. The log line names the booking by its public id."""
    event_id = session.execute(insert(Event).values(venue_id=venue_id, booking_id=booking_id, kind=kind, at=at,
                                                    actor_id=actor_id, data=json.dumps(data or {}))
                               .returning(Event.id)).scalar_one()
    log.info("event kind=%s booking_id=%s actor=%s", kind, booking_public(booking_id), actor_id)
    return event_id