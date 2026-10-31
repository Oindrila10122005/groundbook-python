"""Rows checked here: every request and event reaches the log with public ids and no line carries the club,
settings really do come from an env-file, data survives a restart, the image leaves out everything but the app, and
the README walks one booking from the request to the gate. The container runs themselves (rm + run on the same
volume, an edited env-file, docker logs, docker diff) are run by hand with docker."""
import logging
import re
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from groundbook.app import create_app
from groundbook.clock import get_clock
from groundbook.models import Ground
from groundbook.settings import Settings
from tests.conftest import (
    ROOT,
    T0,
    V,
    booking,
    confirm,
    iso,
    make_settings,
    request,
    requested,
)


def test_every_request_and_event_is_logged_and_no_line_carries_the_club(client, caplog):
    with caplog.set_level(logging.INFO):
        a = requested(client, club="Rafi's XI")
        request(client, "A", "league", "15:00", "17:00", club="Rafi's XI")  #  the refusal path logs too
        confirm(client, a["booking_id"])
        client.get(f"{V}/grounds/A/day?date=2026-10-03")

    lines = [r.getMessage() for r in caplog.records]
    assert "event kind=requested booking_id=BK0001 actor=office" in lines and "event kind=confirmed booking_id=BK0001 actor=office" in lines
    assert not any(re.search(r"booking_id=\d", line) for line in lines), "log lines carry public ids, never database integers"
    assert any("request method=POST path=/bookings status=201" in line for line in lines)
    assert any("request method=POST path=/bookings status=409" in line for line in lines)
    assert any("request method=GET path=/venues/deccan/grounds/A/day status=200" in line for line in lines)
    assert all("Rafi" not in line for line in lines)


def test_settings_come_from_an_env_file(tmp_path, clock, caplog):
    env = tmp_path / ".env"
    db = (tmp_path / "env.db").as_posix()
    env.write_text(f"DATABASE_URL=sqlite:///{db}\nHOLD_HOURS=48\nSEED_DIR={ROOT / 'seed'}\nHOST=127.0.0.2\nPORT=9090\n", encoding="utf-8")
    caplog.set_level(logging.INFO)
    settings = Settings(_env_file=env)
    assert (settings.hold_hours, settings.host, settings.port) == (48, "127.0.0.2", 9090)
    app = create_app(settings)
    app.dependency_overrides[get_clock] = lambda: clock
    with TestClient(app) as c:
        assert c.get("/settings").json()["hold_hours"] == 48
        assert requested(c)["hold_until"] == iso(T0 + timedelta(hours=48))
        assert len(c.get(f"{V}/grounds").json()["grounds"]) == 4
    assert Path(db).exists()
    assert any(r.getMessage().startswith("ready host=127.0.0.2 port=9090 ") for r in caplog.records), "HOST and PORT are read by the settings object"


def test_data_survives_a_restart_on_the_same_database(tmp_path, clock):
    settings = make_settings(tmp_path)
    app = create_app(settings)
    app.dependency_overrides[get_clock] = lambda: clock
    with TestClient(app) as c:
        a = requested(c)
        confirm(c, a["booking_id"])
    app = create_app(settings)
    app.dependency_overrides[get_clock] = lambda: clock
    with TestClient(app) as c:
        b = booking(c, "BK0001")
        assert b["state"] == "confirmed" and [e["kind"] for e in b["events"]] == ["requested", "confirmed"]
        assert [x["booking_id"] for x in c.get(f"{V}/grounds/A/day?date=2026-10-03").json()["bookings"]] == ["BK0001"]
    with app.state.sessionmaker() as s:
        assert s.scalar(select(func.count()).select_from(Ground)) == 4, "the restart did not seed a second complex"


def test_the_env_file_example_lists_every_setting_the_app_reads():
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    keys = [line.split("=")[0] for line in example.splitlines() if line and not line.startswith("#")]
    assert sorted(k.lower() for k in keys) == sorted(Settings.model_fields)
    assert "DATABASE_URL=sqlite:////data/groundbook.db" in example and "SEED_DIR=seed" in example
    assert (Settings.model_fields["host"].default, Settings.model_fields["port"].default) == ("0.0.0.0", 8080)


def test_the_image_leaves_out_everything_but_the_app():
    assert (ROOT / ".dockerignore").read_text(encoding="utf-8").split() == [
        ".git", ".venv", "venv", "**/__pycache__", "**/*.pyc", "**/.pytest_cache", ".ruff_cache", "tests", "sandbox", "**/*.db", ".env",
        "build", "dist", "*.egg-info"]


def test_the_readme_walks_one_booking_from_the_request_to_the_gate():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for needle in ("docker build -t groundbook .", "--env-file .env", "-v groundbook-data:/data", "-p 8080:8080",
                   'CMD ["sh", "-c", "exec uvicorn groundbook.app:app --host \\"$HOST\\" --port \\"$PORT\\""]'):
        assert needle in readme, needle

    curls = [line for line in readme.splitlines() if line.startswith("curl ")]
    assert curls and all("http://localhost:8080/" in line for line in curls), "curl rejects a bare :8080/..."
    steps = [("request", r"-X POST http://localhost:8080/bookings "), ("confirm", r"/bookings/BK0001/confirm"),
             ("day strip", r"/venues/deccan/grounds/A/day\?date="), ("gate", r"curl -s http://localhost:8080/bookings/BK0001\s+# Sabu at the gate")]
    found = [next((i for i, line in enumerate(curls) if re.search(pattern, line)), None) for _, pattern in steps]
    assert None not in found and found == sorted(found), dict(zip([s for s, _ in steps], found))