"""Four grounds with their hours and six event types with their buffers, loaded once; a day read as blocks with
the shadows derived around them -- Sunday on its own hours."""
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from groundbook.app import create_app
from groundbook.clock import get_clock
from groundbook.models import EventType, Ground
from tests.conftest import SAT, SUN, V, day, make_settings

GROUND_A = {"ground": "A", "name": "Ground A", "opens": "06:00", "closes": "22:00", "sunday_opens": "07:00", "sunday_closes": "20:00"}


def test_seeding_is_idempotent_across_two_starts(tmp_path, clock):
    settings = make_settings(tmp_path)
    for _ in range(2):
        app = create_app(settings)
        app.dependency_overrides[get_clock] = lambda: clock
        with TestClient(app) as c:
            assert len(c.get(f"{V}/grounds").json()["grounds"]) == 4
            assert len(c.get(f"{V}/event-types").json()["event_types"]) == 6
    with app.state.sessionmaker() as s:
        assert s.scalar(select(func.count()).select_from(Ground)) == 4, "four, not eight"
        assert s.scalar(select(func.count()).select_from(EventType)) == 6




def test_four_grounds_with_hours_and_six_event_types_with_buffers(client):
    r = client.get(f"{V}/grounds")
    assert r.status_code == 200
    body = r.json()
    assert body["venue"] == "deccan" and [g["ground"] for g in body["grounds"]] == ["A", "B", "C", "D"] and body["grounds"][0] == GROUND_A
    types = client.get(f"{V}/event-types").json()["event_types"]
    assert {t["code"]: (t["setup_minutes"], t["teardown_minutes"]) for t in types} == {
        "practice": (20, 20), "friendly": (30, 20), "league": (40, 30), "athletics": (60, 45), "tournament": (90, 60), "school_day": (120, 120)}
    assert types[0] == {"code": "practice", "name": "Practice", "setup_minutes": 20, "teardown_minutes": 20}


def test_an_unknown_venue_is_404(client):
    for path in ("/venues/mumbai/grounds", "/venues/mumbai/event-types", "/venues/mumbai/grounds/A/day"):
        r = client.get(path)
        assert r.status_code == 404 and r.json()["type"] == "/errors/no-such-venue", path



def test_sunday_uses_the_sunday_hours(client):
    d = day(client, "A", SUN)
    assert d["opens"] == "07:00" and d["closes"] == "20:00" and d["bookings"] == []
    assert day(client, "A", SAT)["opens"] == "06:00"
    assert day(client, "B", "2026-10-11")["opens"] == "07:00", "the next Sunday too"


def test_an_unknown_ground_is_404(client):
    r = client.get(f"{V}/grounds/Z/day")
    assert r.status_code == 404 and r.json()["type"] == "/errors/no-such-ground" and "Z" in r.json()["detail"]


def test_a_bad_date_is_400_validation_and_no_date_means_today(client):
    r = client.get(f"{V}/grounds/A/day?date=2026-13-40")
    assert r.status_code == 400 and r.json()["type"] == "/errors/validation" and r.json()["errors"][0]["field"] == "date"
    assert client.get(f"{V}/grounds/A/day?date=saturday").status_code == 400
    assert client.get(f"{V}/grounds/A/day?date=").status_code == 400, "an empty date is a bad date, not today"
    assert client.get(f"{V}/grounds/A/day").json()["date"] == "2026-10-01", "no date means today: the injected clock's day"


def test_every_response_goes_through_a_declared_model(client):
    spec = client.get("/openapi.json").json()
    for path, ops in spec["paths"].items():
        for op in ops.values():
            ok = [r for code, r in op["responses"].items() if code.startswith("2")]
            assert ok and all("$ref" in r["content"]["application/json"]["schema"] for r in ok), path