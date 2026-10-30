"""A club asks for an interval and an event type; a malformed body (422) is refused differently from an
impossible one (400 bad-interval), and the shadow must fit the ground's hours."""
from datetime import timedelta

from sqlalchemy import func, select

from groundbook.models import Booking
from tests.conftest import CLUB, SAT, SUN, T0, booking, iso, request, requested, ts


def test_a_valid_request_is_201_requested_with_the_shadow_and_a_hold(client, db):
    r = request(client, "A", "league", "14:00", "17:00")
    assert r.status_code == 201, r.text
    assert r.headers["location"] == "/bookings/BK0001"
    assert r.json() == {"booking_id": "BK0001", "ground": "A", "event": "league", "from": ts("14:00"), "to": ts("17:00"),
                        "ground_held_from": ts("13:20"), "ground_held_to": ts("17:30"), "state": "requested", "hold_until": iso(T0 + timedelta(hours=24))}
    with db() as s:
        row = s.get(Booking, 1)
        assert row.state == "requested" and row.club_name == CLUB and row.requested_at.replace(tzinfo=None) == T0.replace(tzinfo=None)
    b = booking(client, "BK0001")
    assert b == {"booking_id": "BK0001", "ground": "A", "event": "league", "from": ts("14:00"), "to": ts("17:00"),
                 "ground_held_from": ts("13:20"), "ground_held_to": ts("17:30"), "state": "requested"}
    assert "club" not in b and "hold_until" not in b


def test_ids_are_opaque_and_sequential(client):
    assert requested(client, "A")["booking_id"] == "BK0001"
    assert requested(client, "B")["booking_id"] == "BK0002"

def test_to_not_after_from_is_400_bad_interval(client, db):
    for frm, to in (("17:00", "14:00"), ("14:00", "14:00")):
        r = request(client, "A", "league", frm, to)
        assert r.status_code == 400 and r.json()["type"] == "/errors/bad-interval", (frm, to, r.text)
        assert "after" in r.json()["detail"]
    with db() as s:
        assert s.scalar(select(func.count()).select_from(Booking)) == 0


def test_a_shadow_outside_the_hours_is_400_bad_interval_naming_the_hours(client):
    r = request(client, "A", "league", "06:20", "08:00")          # setup 40 -> held from 05:40
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["type"] == "/errors/bad-interval" and body["opens"] == "06:00" and body["closes"] == "22:00" and "05:40" in body["detail"]
    r = request(client, "A", "league", "20:00", "21:45")          # teardown 30 -> held to 22:15
    assert r.status_code == 400 and r.json()["closes"] == "22:00"
    assert request(client, "A", "league", "06:40", "08:00").status_code == 201, "06:00 exactly fits"
    r = request(client, "A", "league", "07:00", "09:00", day=SUN)  # Sunday opens 07:00; held from 06:20
    assert r.status_code == 400 and r.json()["opens"] == "07:00"


def test_an_interval_outside_the_hours_is_400_bad_interval(client):
    r = request(client, "A", "league", "05:00", "07:00")
    assert r.status_code == 400 and r.json()["type"] == "/errors/bad-interval" and r.json()["opens"] == "06:00"


def test_nobody_books_the_past(client, clock):
    r = request(client, "A", "league", "14:00", "17:00", day="2026-09-30")
    assert r.status_code == 400 and r.json()["type"] == "/errors/bad-interval" and "past" in r.json()["detail"]
    assert request(client, "A", "league", "07:00", "09:00", day="2026-10-01").status_code == 400, "earlier today is the past too"
    assert request(client, "A", "league", "08:00", "10:00", day="2026-10-01").status_code == 201, "from == now is allowed"


def test_both_ends_on_the_same_date(client):
    r = request(client, "A", "league", "21:00", "01:00")
    assert r.status_code == 400 and r.json()["type"] == "/errors/bad-interval"
    r = client.post("/bookings", json={"ground": "A", "event": "league", "from": ts("20:00", SAT), "to": ts("00:30", SUN), "club": CLUB})
    assert r.status_code == 400 and "same date" in r.json()["detail"]

def test_an_unknown_event_type_is_400_no_such_event_type(client):
    r = request(client, "A", "concert", "14:00", "17:00")
    assert r.status_code == 400 and r.json()["type"] == "/errors/no-such-event-type" and "concert" in r.json()["detail"]


def test_an_unknown_ground_is_404(client):
    r = request(client, "Z", "league", "14:00", "17:00")
    assert r.status_code == 404 and r.json()["type"] == "/errors/no-such-ground"


def test_a_malformed_body_is_422_naming_each_field(client):
    r = client.post("/bookings", json={"ground": "A", "event": "league", "to": ts("17:00"), "club": "X"})
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["type"] == "/errors/validation" and body["status"] == 422
    assert {e["field"] for e in body["errors"]} == {"from", "club"}
    r = client.post("/bookings", json={"ground": "A", "event": "league", "from": "saturday two", "to": ts("17:00"), "club": CLUB})
    assert r.status_code == 422 and r.json()["errors"][0]["field"] == "from"
    assert client.post("/bookings", content="{", headers={"content-type": "application/json"}).status_code == 422

def test_the_length_bounds_are_validation_not_bad_interval(client):
    r = request(client, "A", "league", "14:00", "14:20")
    assert r.status_code == 422 and "30 minutes" in r.json()["errors"][0]["message"]
    r = request(client, "A", "practice", "06:30", "19:00")
    assert r.status_code == 422 and "12 hours" in r.json()["errors"][0]["message"]
    assert request(client, "A", "league", "14:00", "14:30").status_code == 201, "exactly 30 minutes is fine"


def test_an_unknown_booking_is_404(client):
    for bad in ("BK9999", "AS001", "1"):
        r = client.get(f"/bookings/{bad}")
        assert r.status_code == 404 and r.json()["type"] == "/errors/no-such-booking", bad


def test_a_body_names_the_interval_from_and_to_only(client):
    r = client.post("/bookings", json={"ground": "A", "event": "league", "from_at": ts("14:00"), "to_at": ts("17:00"), "club": CLUB})
    assert r.status_code == 422 and {e["field"] for e in r.json()["errors"]} == {"from", "to"}, r.text