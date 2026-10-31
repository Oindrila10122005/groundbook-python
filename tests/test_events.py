"""Every transition writes an event in the same transaction; events can never be updated or deleted; the
booking's events are the only history shown."""
import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError

from groundbook.models import Event
from tests.conftest import (
    CLUB,
    T0,
    at,
    booking,
    cancel,
    confirm,
    iso,
    move,
    requested,
    ts,
)

PKG = Path(__file__).resolve().parent.parent / "groundbook"


def test_a_move_commits_exactly_one_moved_event_with_old_and_new_intervals(client, db):
    a = requested(client, "A", "league", "14:00", "17:00")
    move(client, a["booking_id"], "15:00", "18:00")
    with db() as s:
        rows = s.scalars(select(Event).where(Event.kind == "moved")).all()
        assert len(rows) == 1 and rows[0].booking_id == 1 and rows[0].actor_id == "office"
        assert json.loads(rows[0].data) == {"from": ts("15:00"), "to": ts("18:00"), "previous_from": ts("14:00"), "previous_to": ts("17:00")}


def test_a_failed_move_leaves_no_event(client, db):
    a = requested(client)
    with db() as s:
        before = s.scalar(select(func.count()).select_from(Event))
    with patch("groundbook.services.moves.events.record", side_effect=RuntimeError("boom")):
        assert move(client, a["booking_id"], "15:00", "18:00").status_code == 500
    with db() as s:
        assert s.scalar(select(func.count()).select_from(Event)) == before
    assert [e["kind"] for e in booking(client, a["booking_id"])["events"]] == ["requested"]




def test_a_failed_request_and_a_failed_confirm_leave_no_event_either(client, db):
    with patch("groundbook.services.bookings.events.record", side_effect=RuntimeError("boom")):
        assert client.post("/bookings", json={"ground": "A", "event": "league", "from": ts("14:00"), "to": ts("17:00"), "club": CLUB}).status_code == 500
    with db() as s:
        assert s.scalar(select(func.count()).select_from(Event)) == 0
    assert client.get("/bookings/BK0001").status_code == 404, "the booking row rolled back with its event"
    a = requested(client)
    with patch("groundbook.services.bookings.events.record", side_effect=RuntimeError("boom")):
        assert confirm(client, a["booking_id"]).status_code == 500
    assert booking(client, a["booking_id"])["state"] == "requested"



def test_events_are_append_only(client, db):
    requested(client)
    with db() as s, pytest.raises(DBAPIError):
        s.execute(update(Event).values(kind="edited"))
        s.commit()
    with db() as s, pytest.raises(DBAPIError):
        s.execute(delete(Event))
        s.commit()
    with db() as s, pytest.raises(DBAPIError):
        s.execute(text("DELETE FROM events WHERE id = 1"))
        s.commit()
    with db() as s, pytest.raises(DBAPIError):
        row = s.get(Event, 1)
        row.data = "{}"
        s.commit()
    with db() as s:
        assert s.scalar(select(func.count()).select_from(Event)) == 1 and s.get(Event, 1).kind == "requested"



def test_the_events_model_has_no_update_path():
    """The only write to events is one Core INSERT in services/events.py: no Event object is ever built (so none can be
    changed and flushed), and nothing issues an UPDATE or DELETE against it."""
    src = {str(p.relative_to(PKG)): p.read_text(encoding="utf-8") for p in PKG.rglob("*.py")}
    writes = [name for name, s in src.items() if "insert(Event)" in s]
    assert writes == [str(Path("services") / "events.py")], writes
    for name, s in src.items():
        assert "Event(" not in s.replace("EventType(", "").replace("class Event(", ""), f"{name} builds an Event object"
        assert "update(Event" not in s and "delete(Event" not in s, name


def test_the_timeline_declares_every_fact_an_event_can_carry(client):
    spec = client.get("/openapi.json").json()["components"]["schemas"]["EventOut"]
    assert set(spec["properties"]) == {"at", "kind", "from", "to", "previous_from", "previous_to", "late"}
    assert spec["required"] == ["at", "kind"] and spec.get("additionalProperties") is False
    a = requested(client)
    confirm(client, a["booking_id"])
    events = booking(client, a["booking_id"])["events"]
    assert events[1] == {"at": iso(T0), "kind": "confirmed"}, "absent facts are omitted, never null"




def test_one_bookings_life_in_at_order(client, clock):
    a = requested(client, "A", "league", "14:00", "17:00")                  # at column 72, then a space and Thursday 08:00
    clock.set(at("09:00", "2026-10-01"))
    confirm(client, a["booking_id"])
    clock.set(at("10:00", "2026-10-01"))
    move(client, a["booking_id"], "15:00", "18:00")
    clock.set(at("15:20"))
    cancel(client, a["booking_id"])
    b = booking(client, a["booking_id"])
    assert b["state"] == "cancelled"
    assert b["events"] == [
        {"at": iso(T0), "kind": "requested", "from": ts("14:00"), "to": ts("17:00")},
        {"at": "2026-10-01T09:00:00Z", "kind": "confirmed"},
        {"at": "2026-10-01T10:00:00Z", "kind": "moved", "from": ts("15:00"), "to": ts("18:00"), "previous_from": ts("14:00"), "previous_to": ts("17:00")},
        {"at": ts("15:20"), "kind": "cancelled", "late": True},
    ]


def test_events_carry_ids_intervals_and_facts_never_the_club(client, db, caplog):
    caplog.set_level(logging.INFO)
    a = requested(client, club="Rafi's XI +91 98450 00000 rafi@example.org")
    confirm(client, a["booking_id"])
    with db() as s:
        for row in s.scalars(select(Event)):
            assert "Rafi" not in row.data and "98450" not in row.data and "@" not in row.data
    assert all("Rafi" not in r.getMessage() for r in caplog.records)
    assert "club" not in booking(client, a["booking_id"])