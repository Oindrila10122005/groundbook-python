"""Shared test setup."""
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from groundbook.app import create_app
from groundbook.clock import FixedClock, get_clock
from groundbook.settings import Settings

ROOT = Path(__file__).resolve().parent.parent
T0 = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)      #  and Thursday morning: Rafi rings Deepa about Saturday
SAT = "2026-10-03"
SUN = "2026-10-04"
V = "/venues/deccan"
CLUB = "Ambedkar Nagar CC"


def make_settings(tmp_path: Path, **overrides) -> Settings:
    db = (tmp_path / "groundbook-test.db").as_posix()
    values = {"database_url": f"sqlite:///{db}", "seed_dir": str(ROOT / "seed"), "hold_hours": 24}
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(T0)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def app(settings, clock):
    app = create_app(settings)
    app.dependency_overrides[get_clock] = lambda: clock
    return app


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def db(app):
    """A fresh session factory for looking at rows the API wrote."""
    return app.state.sessionmaker


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def ts(hhmm: str, day: str = SAT) -> str:
    return f"{day}T{hhmm}:00Z"


def request(client, ground="A", event="league", frm="14:00", to="17:00", club=CLUB, day=SAT):
    return client.post("/bookings", json={"ground": ground, "event": event, "from": ts(frm, day), "to": ts(to, day), "club": club})


def requested(client, ground="A", event="league", frm="14:00", to="17:00", club=CLUB, day=SAT) -> dict:
    r = request(client, ground, event, frm, to, club, day)
    assert r.status_code == 201, r.text
    return r.json()


def booking(client, booking_id) -> dict:
    r = client.get(f"/bookings/{booking_id}")
    assert r.status_code == 200, r.text
    return r.json()


def day(client, ground="A", date=SAT) -> dict:
    r = client.get(f"{V}/grounds/{ground}/day?date={date}")
    assert r.status_code == 200, r.text
    return r.json()