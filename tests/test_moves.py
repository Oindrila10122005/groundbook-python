"""A move re-checks the whole new interval, buffers included, excluding itself, and is one transaction."""
from sqlalchemy import func, select, text
from groundbook.models import Booking, Event

from tests.conftest import (
    T0,
    at,
    booking,
    cancel,
    confirm,
    day,
    iso,
    move,
    request,
    requested,
    ts,
)


def test_a_move_into_a_clash_is_409_and_the_booking_stays_where_it_was(client, db):
    a = requested(client, "A", "league", "14:00", "17:00")
    b = requested(client, "A", "league", "18:30", "20:30")              # and held 17:50-21:00: clear of A's 17:30
    r = move(client, a["booking_id"], "15:00", "18:00")                 # and would be held to 18:30
    assert r.status_code == 409, r.text
    assert r.json()["type"] == "/errors/overlap"
    assert r.json()["clashes_with"] == [{"booking_id": b["booking_id"], "ground_held_from": ts("17:50"), "ground_held_to": ts("21:00")}]
    got = booking(client, a["booking_id"])
    assert got["from"] == ts("14:00") and got["to"] == ts("17:00") and [e["kind"] for e in got["events"]] == ["requested"]
    with db() as s:
        row = s.get(Booking, 1)
        assert row.moved_at is None and row.previous_from is None




def test_a_valid_move_releases_the_old_interval_and_takes_the_new_one_in_one_row(client, clock, db):
    a = requested(client, "A", "league", "14:00", "17:00")
    clock.advance(hours=2)
    r = move(client, a["booking_id"], "15:00", "18:00")
    assert r.status_code == 200, r.text
    assert r.json() == {"booking_id": "BK0001", "from": ts("15:00"), "to": ts("18:00"), "ground_held_from": ts("14:20"), "ground_held_to": ts("18:30"),
                        "moved_at": iso(at("10:00", "2026-10-01"))}
    blocks = day(client, "A")["bookings"]
    assert [(x["booking_id"], x["from"]) for x in blocks] == [("BK0001", ts("15:00"))], "in its new place, never both"
    assert request(client, "A", "league", "11:00", "13:30").status_code == 201, "held to 14:00: the old 13:20 start is free"
    assert request(client, "A", "league", "18:30", "20:00").status_code == 409, "held from 17:50: the new 18:30 end is taken"
    with db() as s:
        assert s.scalar(select(func.count()).select_from(Booking).where(Booking.ground_id == 1)) == 2
        row = s.get(Booking, 1)
        assert row.previous_from.replace(tzinfo=None) == at("14:00").replace(tzinfo=None) and row.previous_to.replace(tzinfo=None) == at("17:00").replace(tzinfo=None)




def test_a_failure_injected_after_the_check_rolls_the_move_back(client, db):
    a = requested(client, "A", "league", "14:00", "17:00")
    with db() as s:   # and the database refuses the move's own write, after the clash check has passed
        s.execute(text("CREATE TRIGGER fail_move BEFORE UPDATE ON bookings WHEN NEW.from_at IS NOT OLD.from_at "
                       "BEGIN SELECT RAISE(ABORT, 'injected failure'); END"))
        s.commit()
    r = move(client, a["booking_id"], "15:00", "18:00")
    with db() as s:
        s.execute(text("DROP TRIGGER fail_move"))
        s.commit()
        assert r.status_code == 500 and r.json()["type"] == "/errors/internal"
    got = booking(client, a["booking_id"])
    assert got["from"] == ts("14:00") and got["to"] == ts("17:00") and got["ground_held_from"] == ts("13:20")
    with db() as s:
        row = s.get(Booking, 1)
        assert row.moved_at is None and row.previous_from is None
        assert s.scalar(select(func.count()).select_from(Event)) == 1
    assert move(client, a["booking_id"], "15:00", "18:00").status_code == 200, "nothing was left half-done"



def test_a_move_after_from_is_409_already_started(client, clock):
    a = requested(client, "A", "league", "14:00", "17:00")
    clock.set(at("14:01"))
    r = move(client, a["booking_id"], "15:00", "18:00")
    assert r.status_code == 409 and r.json()["type"] == "/errors/already-started"
    assert booking(client, a["booking_id"])["from"] == ts("14:00")


def test_a_cancelled_booking_cannot_be_moved(client):
    a = requested(client)
    cancel(client, a["booking_id"])
    r = move(client, a["booking_id"], "15:00", "18:00")
    assert r.status_code == 409 and r.json()["type"] == "/errors/cancelled"



def test_a_move_to_a_bad_interval_is_400_and_a_malformed_move_is_422(client):
    a = requested(client, "A", "league", "14:00", "17:00")
    r = move(client, a["booking_id"], "18:00", "15:00")
    assert r.status_code == 400 and r.json()["type"] == "/errors/bad-interval"
    r = move(client, a["booking_id"], "06:00", "08:00")
    assert r.status_code == 400 and r.json()["opens"] == "06:00"
    r = move(client, a["booking_id"], "14:00", "17:00", day="2026-09-30")
    assert r.status_code == 400 and "past" in r.json()["detail"]
    r = move(client, a["booking_id"], "15:00", "15:10")
    assert r.status_code == 422 and r.json()["type"] == "/errors/validation"
    r = client.post(f"/bookings/{a['booking_id']}/move", json={"from": ts("15:00")})
    assert r.status_code == 422 and r.json()["errors"][0]["field"] == "to"
    assert booking(client, a["booking_id"])["from"] == ts("14:00")



def test_moving_keeps_the_state(client):
    a = requested(client, "A", "league", "14:00", "17:00")
    move(client, a["booking_id"], "15:00", "18:00")
    assert booking(client, a["booking_id"])["state"] == "requested"
    confirm(client, a["booking_id"])
    assert move(client, a["booking_id"], "16:00", "19:00").status_code == 200
    assert booking(client, a["booking_id"])["state"] == "confirmed"


def test_a_move_excludes_itself_from_the_clash_check(client):
    a = requested(client, "A", "league", "14:00", "17:00")
    r = move(client, a["booking_id"], "14:30", "17:30")                 # overlaps its own old shadow entirely
    assert r.status_code == 200, r.text
    assert booking(client, a["booking_id"])["ground_held_from"] == ts("13:50")


def test_moving_an_unknown_booking_is_404(client):
    r = move(client, "BK0042", "15:00", "18:00")
    assert r.status_code == 404 and r.json()["type"] == "/errors/no-such-booking"


def test_the_moved_at_is_the_clock(client, clock):
    a = requested(client)
    clock.advance(days=1)
    assert move(client, a["booking_id"], "15:00", "18:00").json()["moved_at"] == iso(T0.replace(day=2))