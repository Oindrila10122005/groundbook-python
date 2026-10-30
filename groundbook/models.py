"""Venues, grounds and event types. A shadow is never stored: there is deliberately no held_from / held_to
column anywhere."""
"""Venues, grounds, event types and bookings. A booking's shadow (interval +/- the event type's buffers)
is computed on read from these rows; there is deliberately no held_from / held_to column anywhere."""
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Venue(Base):
    __tablename__ = "venues"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(80))




class Ground(Base):
    """Opening hours as HH:MM strings; Sunday has its own pair. A ground's code is unique within its venue by
    the seed's existence check, not by a constraint."""
    __tablename__ = "grounds"
    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"))
    code: Mapped[str] = mapped_column(String(8))
    name: Mapped[str] = mapped_column(String(60))
    opens: Mapped[str] = mapped_column(String(5))
    closes: Mapped[str] = mapped_column(String(5))
    sunday_opens: Mapped[str] = mapped_column(String(5))
    sunday_closes: Mapped[str] = mapped_column(String(5))


class EventType(Base):
    """The buffers live here, per event type -- the source of every shadow."""
    __tablename__ = "event_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"))
    code: Mapped[str] = mapped_column(String(24))
    name: Mapped[str] = mapped_column(String(60))
    setup_minutes: Mapped[int] = mapped_column(Integer)
    teardown_minutes: Mapped[int] = mapped_column(Integer)



class Booking(Base):
    """One row per request. The interval is [from_at, to_at); the shadow is derived."""
    __tablename__ = "bookings"
    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"))
    ground_id: Mapped[int] = mapped_column(ForeignKey("grounds.id"))
    event_type_id: Mapped[int] = mapped_column(ForeignKey("event_types.id"))
    club_name: Mapped[str] = mapped_column(String(80))
    from_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    to_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(12))                     # requested | confirmed | cancelled | expired
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    hold_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))