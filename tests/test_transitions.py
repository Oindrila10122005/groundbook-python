"""Confirm and cancel are real transitions whose rules read the injected clock."""
from datetime import timedelta

from groundbook.clock import get_clock
from groundbook.db import get_session
from groundbook.models import Booking
from tests.conftest import T0, at, booking, cancel, confirm, day, iso, requested


def test_requested_before_from_confirms(client, clock, db):
    b = requested(client)
    clock.advance(hours=1)
    r = confirm(client, b["booking_id"])
    assert r.status_code == 200, r.text
    assert r.json() == {"booking_id": "BK0001", "state": "confirmed", "confirmed_at": iso(T0 + timedelta(hours=1))}
    assert booking(client, "BK0001")["state"] == "confirmed"
    with db() as s:
        assert s.get(Booking, 1).confirmed_at.replace(tzinfo=None) == (T0 + timedelta(hours=1)).replace(tzinfo=None)




def test_confirm_after_from_is_409_already_started(client, clock):
    b = requested(client, frm="14:00", to="17:00")
    clock.set(at("14:20"))
    r = confirm(client, b["booking_id"])
    assert r.status_code == 409 and r.json()["type"] == "/errors/already-started"
    assert booking(client, "BK0001")["state"] == "requested"
    clock.set(at("14:00"))
    assert confirm(client, b["booking_id"]).status_code == 409, "from itself has begun (half-open)"


def test_confirm_twice_is_409_already_confirmed(client):
    b = requested(client)
    assert confirm(client, b["booking_id"]).status_code == 200
    r = confirm(client, b["booking_id"])
    assert r.status_code == 409 and r.json()["type"] == "/errors/already-confirmed"



def test_cancel_twenty_minutes_after_from_is_a_late_cancel(client, clock, db):
    b = requested(client, frm="14:00", to="17:00")
    confirm(client, b["booking_id"])
    clock.set(at("14:20"))
    r = cancel(client, b["booking_id"])
    assert r.status_code == 200, r.text
    assert r.json() == {"booking_id": "BK0001", "state": "cancelled", "cancelled_at": at("14:20").strftime("%Y-%m-%dT%H:%M:%SZ"), "late": True}
    with db() as s:
        assert s.get(Booking, 1).late_cancel is True and s.get(Booking, 1).state == "cancelled"
    assert booking(client, "BK0001")["state"] == "cancelled"


def test_cancel_before_from_is_not_late(client, clock):
    b = requested(client)
    r = cancel(client, b["booking_id"])
    assert r.status_code == 200 and r.json()["late"] is False and r.json()["cancelled_at"] == iso(T0)


def test_cancel_after_to_is_409_already_over(client, clock):
    b = requested(client, frm="14:00", to="17:00")
    clock.set(at("17:00"))
    r = cancel(client, b["booking_id"])
    assert r.status_code == 409 and r.json()["type"] == "/errors/already-over"
    clock.set(at("16:59"))
    assert cancel(client, b["booking_id"]).status_code == 200



def test_cancel_twice_is_409_already_cancelled(client):
    b = requested(client)
    cancel(client, b["booking_id"])
    r = cancel(client, b["booking_id"])
    assert r.status_code == 409 and r.json()["type"] == "/errors/already-cancelled"


def test_a_cancelled_booking_cannot_be_confirmed(client):
    b = requested(client)
    cancel(client, b["booking_id"])
    r = confirm(client, b["booking_id"])
    assert r.status_code == 409 and r.json()["type"] == "/errors/cancelled"


def test_a_late_cancel_keeps_the_block_on_the_strip(client, clock):
    b = requested(client, frm="14:00", to="17:00")
    clock.set(at("14:20"))
    cancel(client, b["booking_id"])
    blocks = day(client, "A")["bookings"]
    assert len(blocks) == 1 and blocks[0]["state"] == "cancelled", "the strip does not show the hour as free"
    assert booking(client, b["booking_id"])["events"][-1] == {"at": at("14:20").strftime("%Y-%m-%dT%H:%M:%SZ"), "kind": "cancelled", "late": True}


def test_the_clock_and_the_session_are_depends_on_every_transition(app):
    for route in app.routes:
        if getattr(route, "path", "").startswith("/bookings") and "POST" in getattr(route, "methods", set()):
            calls = {d.call for d in route.dependant.dependencies}
            assert get_clock in calls and get_session in calls, route.path


def test_the_404s(client):
    for action in ("confirm", "cancel"):
        r = client.post(f"/bookings/BK0042/{action}")
        assert r.status_code == 404 and r.json()["type"] == "/errors/no-such-booking"