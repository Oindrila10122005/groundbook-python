"""Overlap is refused once the buffers are counted on both sides, a cancelled booking cannot be reconfirmed,
and every refusal is raised in the service and mapped by one handler."""
import ast
from pathlib import Path

from sqlalchemy import func, select

from groundbook.handlers import PROBLEM
from groundbook.models import Booking
from tests.conftest import booking, cancel, confirm, request, requested, ts

PKG = Path(__file__).resolve().parent.parent / "groundbook"


def test_back_to_back_on_paper_overlaps_once_the_buffers_are_counted(client, db):
    a = requested(client, "A", "league", "14:00", "16:00")              #  and held 13:20-16:30
    r = request(client, "A", "league", "16:00", "18:00")                #  and held from 15:20
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["type"] == "/errors/overlap" and body["status"] == 409
    assert body["clashes_with"] == [{"booking_id": a["booking_id"], "ground_held_from": ts("13:20"), "ground_held_to": ts("16:30")}]
    with db() as s:
        assert s.scalar(select(func.count()).select_from(Booking)) == 1, "nothing written"




def test_a_request_clear_of_every_shadow_is_201(client):
    requested(client, "A", "league", "14:00", "16:00")                  # and held to 16:30
    r = request(client, "A", "league", "17:00", "19:00")                # and held from 16:20 -- wait, that touches
    assert r.status_code == 409
    r = request(client, "A", "league", "17:10", "19:00")                # and held from 16:30: half-open, just fits
    assert r.status_code == 201, r.text
    assert r.json()["ground_held_from"] == ts("16:30")


def test_both_buffers_count_on_both_sides(client):
    requested(client, "A", "league", "14:00", "16:00")                  # and held 13:20-16:30
    left = request(client, "A", "league", "12:00", "13:30")             # and held to 14:00 > 13:20: the new teardown meets the old setup
    assert left.status_code == 409 and left.json()["type"] == "/errors/overlap"
    right = request(client, "A", "league", "16:30", "18:00")            # and held from 15:50 < 16:30: the new setup meets the old teardown
    assert right.status_code == 409
    inside = request(client, "A", "practice", "14:30", "15:00")
    assert inside.status_code == 409 and inside.json()["clashes_with"][0]["booking_id"] == "BK0001"
    assert request(client, "A", "league", "11:00", "12:30").status_code == 201, "held to 13:00 < 13:20"



def test_a_booking_on_another_ground_or_day_never_clashes(client):
    requested(client, "A", "league", "14:00", "16:00")
    assert request(client, "B", "league", "14:00", "16:00").status_code == 201
    assert request(client, "A", "league", "14:00", "16:00", day="2026-10-10").status_code == 201


def test_only_live_bookings_hold_the_ground(client, clock):
    a = requested(client, "A", "league", "14:00", "16:00")
    assert request(client, "A", "league", "14:00", "16:00").status_code == 409, "a requested booking within its hold is live"
    clock.advance(hours=25)                                             # and the hold has lapsed; nothing swept it yet
    b = request(client, "A", "league", "14:00", "16:00")
    assert b.status_code == 201, "an expired hold holds nothing"
    cancel(client, b.json()["booking_id"])
    c = request(client, "A", "league", "14:00", "16:00")
    assert c.status_code == 201, "a cancelled booking holds nothing"
    confirm(client, c.json()["booking_id"])
    d = request(client, "A", "league", "14:00", "16:00")
    assert d.status_code == 409 and d.json()["clashes_with"][0]["booking_id"] == c.json()["booking_id"], "a confirmed one always does"
    assert a["booking_id"] not in [x["booking_id"] for x in d.json()["clashes_with"]]



def test_confirm_re_runs_the_check_because_a_competing_request_may_have_won(client, clock):
    a = requested(client, "A", "league", "14:00", "16:00")
    clock.advance(hours=25)
    b = requested(client, "A", "league", "15:00", "17:00")
    r = confirm(client, a["booking_id"])
    assert r.status_code == 409 and r.json()["type"] == "/errors/overlap"
    assert r.json()["clashes_with"] == [{"booking_id": b["booking_id"], "ground_held_from": ts("14:20"), "ground_held_to": ts("17:30")}]
    assert booking(client, a["booking_id"])["state"] == "requested"
    assert confirm(client, b["booking_id"]).status_code == 200, "the check excludes the booking itself"


def test_a_cancelled_booking_cannot_be_reconfirmed(client):
    a = requested(client)
    cancel(client, a["booking_id"])
    r = confirm(client, a["booking_id"])
    assert r.status_code == 409 and r.json()["type"] == "/errors/cancelled" and "request a new" in r.json()["detail"]



def test_refusal_body_has_exactly_the_documented_shape(client, clock):
    requested(client, "A", "league", "14:00", "16:00")
    r = request(client, "A", "league", "16:00", "18:00")
    assert r.headers["content-type"].startswith(PROBLEM)
    assert set(r.json()) == {"type", "title", "status", "detail", "clashes_with"}
    assert set(r.json()["clashes_with"][0]) == {"booking_id", "ground_held_from", "ground_held_to"}
    r = request(client, "A", "league", "06:20", "08:00")
    assert set(r.json()) == {"type", "title", "status", "detail", "opens", "closes"}
    r = request(client, "A", "league", "17:00", "14:00")
    assert set(r.json()) == {"type", "title", "status", "detail"}
    clock.advance(days=3)
    r = confirm(client, "BK0001")
    assert set(r.json()) == {"type", "title", "status", "detail"} and r.json()["title"] and "Traceback" not in r.text



def test_refusals_are_raised_in_the_service_and_mapped_by_one_handler():
    for path in (PKG / "routers").glob("*.py"):
        src = path.read_text(encoding="utf-8")
        assert "HTTPException" not in src and "JSONResponse" not in src, path.name
        assert not any(isinstance(n, ast.Raise) for n in ast.walk(ast.parse(src))), f"{path.name} raises inside a route"
    services = "".join(p.read_text(encoding="utf-8") for p in (PKG / "services").glob("*.py"))
    for cls in ("Overlap", "Cancelled", "AlreadyStarted", "AlreadyOver", "BadInterval"):
        assert f"raise {cls}(" in services, cls
    handlers = (PKG / "handlers.py").read_text(encoding="utf-8")
    assert handlers.count("@app.exception_handler(DomainError)") == 1
    app_src = (PKG / "app.py").read_text(encoding="utf-8")
    assert "exception_handler" not in app_src and "install_handlers(app)" in app_src