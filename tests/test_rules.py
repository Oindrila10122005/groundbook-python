"""One parametrised table of every refusal, run with the clock overridden under two buffer tables -- the old
uniform 40/30 for every event type, and the per-type table in seed/ -- and only the rows tagged `buffer` move."""
"""The rule table: every refusal the planner can give, run under two buffer tables."""
import csv
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from groundbook.app import create_app
from groundbook.clock import get_clock
from groundbook.settings import Settings
from tests.conftest import ROOT, SAT, at, make_settings, ts

ROWS = list(csv.DictReader((Path(__file__).parent / "rules.csv").open(encoding="utf-8")))
#  and the rule change is a settings override: which seed directory the event types (and their buffers) are read from.
SEEDS = {"uniform": str(Path(__file__).parent / "seed_uniform"), "per_type": str(ROOT / "seed")}
PER_TYPE = {"practice": [20, 20], "friendly": [30, 20], "league": [40, 30], "athletics": [60, 45], "tournament": [90, 60], "school_day": [120, 120]}



def booking_ref(ref: str, ids: list[str]) -> str:
    """`1` is the first booking this case created; a literal `BK…` id is used as it is (an unknown booking)."""
    return ref if ref.startswith("BK") else ids[int(ref) - 1]


def step(client, clock, text, ids):
    verb, *args = text.split()
    if verb == "request":
        r = client.post("/bookings", json={"ground": args[0], "event": args[1], "from": ts(args[2]), "to": ts(args[3]), "club": "Ambedkar Nagar CC"})
        if r.status_code == 201:
            ids.append(r.json()["booking_id"])
        return r
    if verb == "request_without_from":
        return client.post("/bookings", json={"ground": args[0], "event": args[1], "to": ts(args[2]), "club": "Ambedkar Nagar CC"})
    if verb in ("confirm", "cancel"):
        return client.post(f"/bookings/{booking_ref(args[0], ids)}/{verb}")
    if verb == "move":
        return client.post(f"/bookings/{booking_ref(args[0], ids)}/move", json={"from": ts(args[1]), "to": ts(args[2])})
    if verb == "day":
        return client.get(f"/venues/deccan/grounds/{args[0]}/day?date={args[1]}")
    if verb == "grounds":
        return client.get(f"/venues/{args[0]}/grounds")
    if verb == "clock":
        clock.set(at(args[1], {"sat": SAT}[args[0]]))
        return None
    raise ValueError(text)



def run_case(client, clock, row):
    ids: list[str] = []
    for text in filter(None, row["setup"].split(";")):
        r = step(client, clock, text, ids)
        assert r is None or r.status_code in (200, 201), (text, r.text)
    return step(client, clock, row["action"], ids)


@pytest.mark.parametrize("mode", list(SEEDS))
@pytest.mark.parametrize("row", ROWS, ids=[r["case"] for r in ROWS])
def test_rule_table(tmp_path, clock, row, mode):
    app = create_app(make_settings(tmp_path, seed_dir=SEEDS[mode]))
    app.dependency_overrides[get_clock] = lambda: clock
    with TestClient(app) as client:
        r = run_case(client, clock, row)
    assert r.status_code == int(row[f"status_{mode}"]), (row["case"], mode, r.text)
    expected_type = row[f"type_{mode}"]
    if expected_type:
        assert r.json()["type"] == expected_type
    if row["case"] == "late_cancel":
        assert r.json()["late"] is True
    if row["case"] == "shadow_outside_hours":
        assert r.json()["opens"] == "06:00"



def test_only_buffer_rows_move_when_the_buffers_change():
    def outcome(r, mode):
        return (r[f"status_{mode}"], r[f"type_{mode}"])
    moved = {r["case"] for r in ROWS if outcome(r, "uniform") != outcome(r, "per_type")}
    assert moved == {r["case"] for r in ROWS if r["tag"] == "buffer"} == {"practice_after_league", "school_day_after_league"}
    practice = next(r for r in ROWS if r["case"] == "practice_after_league")
    school = next(r for r in ROWS if r["case"] == "school_day_after_league")
    assert outcome(practice, "per_type") == ("201", "") and outcome(school, "per_type") == ("409", "/errors/overlap"), \
        "twenty minutes is enough for a practice; a sports day needs two hours"


def test_every_refusal_type_has_a_row():
    types = {r[f"type_{m}"] for r in ROWS for m in SEEDS} - {""}
    assert types == {"/errors/bad-interval", "/errors/validation", "/errors/no-such-event-type", "/errors/no-such-ground", "/errors/no-such-venue",
                     "/errors/no-such-booking", "/errors/overlap", "/errors/already-started", "/errors/already-confirmed", "/errors/already-over",
                     "/errors/already-cancelled", "/errors/cancelled"}, "every refusal type has a row"
    assert {r["case"] for r in ROWS} == {"ok", "to_before_from", "outside_hours", "shadow_outside_hours", "malformed", "bad_day_date",
                                         "no_such_event_type", "no_such_ground", "no_such_venue", "overlap_left_buffer", "overlap_right_buffer",
                                         "back_to_back_just_fits", "confirm_ok", "confirm_started", "confirm_twice", "cancel_over", "late_cancel",
                                         "cancel_twice", "reconfirm_cancelled", "no_such_booking", "move_into_clash", "move_ok",
                                         "practice_after_league", "school_day_after_league"}
    statuses = {int(r[f"status_{m}"]) for r in ROWS for m in SEEDS if r[f"type_{m}"] == "/errors/validation"}
    assert statuses == {400, 422}, "a bad query parameter is 400, a bad body 422 -- both rows run"



def test_the_rule_book_shows_the_rows_the_tests_run():
    """The Rule book screen holds its own copy of the table (app.js RULES); it must say exactly what rules.csv says."""
    js = (ROOT / "groundbook" / "static" / "app.js").read_text(encoding="utf-8")
    shown = json.loads(re.search(r"var RULES = (\[.*?\n  \]);", js, re.DOTALL).group(1))
    assert [(r[0], r[1], str(r[3]), r[4], str(r[5]), r[6]) for r in shown] == \
        [(r["case"], r["tag"], r["status_uniform"], r["type_uniform"], r["status_per_type"], r["type_per_type"]) for r in ROWS]


def test_settings_endpoint_shows_the_live_buffer_table(client, tmp_path, clock):
    assert client.get("/settings").json() == {"hold_hours": 24, "buffers": PER_TYPE}
    (tmp_path / "uniform").mkdir()                                      # its own database: seeding is idempotent, so the client's file already holds the per-type table
    app = create_app(make_settings(tmp_path / "uniform", seed_dir=SEEDS["uniform"], hold_hours=12))
    app.dependency_overrides[get_clock] = lambda: clock
    with TestClient(app) as c:
        body = c.get("/settings").json()
        assert body["hold_hours"] == 12 and set(map(tuple, body["buffers"].values())) == {(40, 30)}


def test_the_buffers_come_from_the_event_types_not_a_setting(client):
    assert "default_buffer" not in " ".join(Settings.model_fields) and "DEFAULT_BUFFER" not in (ROOT / "groundbook" / "settings.py").read_text(encoding="utf-8")
    types = client.get("/venues/deccan/event-types").json()["event_types"]
    assert client.get("/settings").json()["buffers"] == {t["code"]: [t["setup_minutes"], t["teardown_minutes"]] for t in types}