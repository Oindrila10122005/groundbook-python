"""Venues, grounds, event types, bookings and the event log. A booking's shadow (interval +/- the event type's buffers)
is computed on read from these rows; there is deliberately no held_from / held_to column anywhere."""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
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
    """One row per request. The interval is [from_at, to_at); the shadow is derived. It also holds the transition
    stamps and the last move (the full history is the events table)."""
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
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    late_cancel: Mapped[bool] = mapped_column(Boolean, default=False)
    moved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    previous_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    previous_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Event(Base):
    """One row per transition, written in the same transaction as the change. Insert only."""
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"))
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"))
    kind: Mapped[str] = mapped_column(String(16))                      # requested | confirmed | moved | cancelled | expired | charged | invoiced | rechecked
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_id: Mapped[str] = mapped_column(String(16))                  # who did it: the office (requests carry no identity)
    data: Mapped[str] = mapped_column(Text, default="{}")              # JSON: ids, intervals and facts -- never the club's phone or email