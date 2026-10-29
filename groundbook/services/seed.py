"""Load the venue, its four grounds with their hours and the six event types with their buffers once, before
the first request. Idempotent: a second start changes nothing."""
"""Fills the database with its starting data."""

import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import EventType, Ground, Venue

VENUE = ("deccan", "Deccan Sports Complex")


def seed(session: Session, seed_dir: str) -> None:
    venue = session.scalar(select(Venue).where(Venue.slug == VENUE[0]))
    if venue is None:
        venue = Venue(slug=VENUE[0], name=VENUE[1])
        session.add(venue)
        session.flush()

    if session.scalar(select(Ground.id).where(Ground.venue_id == venue.id).limit(1)) is None:
        with (Path(seed_dir) / "grounds.csv").open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                session.add(Ground(venue_id=venue.id, code=row["code"], name=row["name"], opens=row["opens"], closes=row["closes"],
                                   sunday_opens=row["sunday_opens"], sunday_closes=row["sunday_closes"]))
    if session.scalar(select(EventType.id).where(EventType.venue_id == venue.id).limit(1)) is None:
        with (Path(seed_dir) / "event_types.csv").open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                session.add(EventType(venue_id=venue.id, code=row["code"], name=row["name"],
                                      setup_minutes=int(row["setup_minutes"]), teardown_minutes=int(row["teardown_minutes"])))
    session.commit()