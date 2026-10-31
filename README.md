# GroundBook

A municipal sports complex: four grounds, a wall planner in Sabu's office, and two clubs who twice arrived at the
same ground on the same Saturday because the pencil marks show the match and never the forty minutes of setup
around it. This folder is the state of the project at the end of its last ticket: a booking
casts its own shadow, and no two shadows may ever touch.

## What is here

| Part | What it does |
|---|---|
| Grounds | Four grounds with weekday and Sunday hours and six event types with setup/teardown buffers, loaded once from `seed/`; `GET /venues/deccan/grounds`, `GET …/event-types`, `GET …/grounds/{ground}/day?date=` — blocks in `from` order, each with `ground_held_from`/`ground_held_to` computed on read, never stored |
| Requests | `POST /bookings` with real constraints: a malformed body is 422 naming each field; a valid body that asks the impossible (`to` ≤ `from`, the past, two dates, a shadow outside the hours) is 400 bad-interval with `opens`/`closes`; `hold_until` from `HOLD_HOURS`; `Location` on the 201 |
| Confirm and cancel | `POST /bookings/{id}/confirm` and `…/cancel` against an injected clock: already-started, already-over, already-confirmed, already-cancelled; a cancel after `from` is allowed and flagged `late` |
| Clashes | The clash predicate on shadows, half-open, both buffers — 409 overlap with `clashes_with`; a cancelled booking cannot be reconfirmed (409 cancelled); confirm re-runs the check; one handler maps every refusal |
| Moves | `POST /bookings/{id}/move`: the whole new interval re-checked with the booking itself excluded, the old interval released and the new one taken in one UPDATE, all or nothing |
| Events | An append-only event log per booking — requested, confirmed, moved (old and new intervals), cancelled (late or not) — written with one INSERT in the same transaction as the change; the database refuses UPDATE and DELETE; `GET /bookings/{id}` returns the timeline |
| The API | Routers per resource (grounds, bookings, moves), one error shape for every error — the refusals, an unknown path (404), a wrong method (405) and the unexpected (500) — and docs that list exactly the answers each call can give |
| Rules | `tests/rules.csv` — 24 cases under two buffer tables (uniform 40/30, per event type), every refusal type among them; only the two rows tagged `buffer` move; `GET /settings` shows the hold and the live buffer table |
| The image | A Dockerfile from `python:3.12-slim` installing a complete lock file, `HOST=0.0.0.0`, `PORT=8080`, the day strip reachable from Sabu's gate tablet |
| Running it | Data on a volume, every setting from an env-file, `.dockerignore`, one log line per request and per event on stdout |

## Run it

```bash
docker build -t groundbook .
cp .env.example .env
docker run -d --name groundbook -p 8080:8080 -v groundbook-data:/data --env-file .env groundbook
```

The image starts the app with

```
CMD ["sh", "-c", "exec uvicorn groundbook.app:app --host \"$HOST\" --port \"$PORT\""]
```

— the image's command, with the address and port read from `HOST` and `PORT`: the Dockerfile sets them to `0.0.0.0` and
`8080`, and the env-file may change them. The database path is not baked into the image; the env-file names it.

Open `http://<office-pc-ip>:8080/` from the gate tablet — the day (four strips with their shadows), the Book
screen, one booking's card, the rule book, the API and the runtime, with a walkthrough. Docs at
`/docs`, health at `/healthz`, logs with `docker logs -f groundbook`.

The Friday update: `docker rm -f groundbook`, then the same `docker run` — Saturday's bookings are all there, because
the database lives on the `groundbook-data` volume (the Runtime screen's Before restart / After restart buttons
compare Saturday across the restart). To change a rule, edit `.env` and restart; no rebuild:

```
DATABASE_URL=sqlite:////data/groundbook.db
HOLD_HOURS=24          # after this many hours a requested slot no longer holds the ground
SEED_DIR=seed
HOST=0.0.0.0
PORT=8080
```

## Verified on this build

Run with Docker Desktop on the build machine on <date> (image tag `groundbook`, host port 8080, a fresh and
named volume, a copy of `.env.example` as the env-file).

- `docker build` → ok; image <size> MB; its Env holds `HOST=0.0.0.0` and `PORT=8080`.
- `/healthz` → 200 `{"status":"ok"}` from the host and from a second container through `host.docker.internal`;
  `/venues/deccan/grounds` from the second container → 200, grounds A–D.
- The `curl` calls above, in order: 201 with `Location: /bookings/<id>`, confirm 200, the strip, the gate read.
- A booking requested, confirmed and moved; `docker rm -f` and the same `docker run` on the same volume →
  `GET /bookings/<id>` 200 with its three events, the other Saturday booking unchanged; the Runtime screen's
  After restart said "unchanged".
- `HOLD_HOURS=48` in a copy of the env-file, restart → `GET /settings` shows 48 and a new request is held 48 hours.
- `docker logs` → one line per request and one per event (`booking_id=<id>`, never a database integer), no club
  name; `docker diff` → only the `/data` mount point, nothing under `/app`.
- `pip freeze` in the image → the 17 pins of `requirements.lock`, exactly; no `__pycache__`, `*.db`, `tests` or
  `sandbox` under `/app`.

## Run it locally

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt
python -m uvicorn groundbook.app:app --host 127.0.0.1 --port 8080
python -m pytest            # 133 tests, each on its own SQLite file with a clock it controls
```

## One booking, request to the gate

```bash
curl -s -i -X POST http://localhost:8080/bookings -H 'content-type: application/json' \
  -d '{"ground":"A","event":"league","from":"2026-10-03T14:00:00Z","to":"2026-10-03T17:00:00Z","club":"Ambedkar Nagar CC"}'
# 201, Location: /bookings/BK0001
# {"booking_id":"BK0001","ground":"A","event":"league","from":"2026-10-03T14:00:00Z","to":"2026-10-03T17:00:00Z",
#  "ground_held_from":"2026-10-03T13:20:00Z","ground_held_to":"2026-10-03T17:30:00Z","state":"requested","hold_until":"…"}
curl -s -X POST http://localhost:8080/bookings/BK0001/confirm       # {"booking_id":"BK0001","state":"confirmed","confirmed_at":"…"}
curl -s 'http://localhost:8080/venues/deccan/grounds/A/day?date=2026-10-03'   # the strip: one block 14:00–17:00, held 13:20–17:30, confirmed
curl -s http://localhost:8080/bookings/BK0001                       # Sabu at the gate: the booking, its held range and its timeline
```

Then, if the club rings again:

```bash
curl -s -X POST http://localhost:8080/bookings/BK0001/move -H 'content-type: application/json' -d '{"from":"2026-10-03T15:00:00Z","to":"2026-10-03T18:00:00Z"}'
curl -s -X POST http://localhost:8080/bookings/BK0001/cancel        # {"booking_id":"BK0001","state":"cancelled","cancelled_at":"…","late":false}
```

Refusals to try: request 16:00–18:00 after a league 14:00–16:00 → 409 overlap naming the booking and its held range
(on paper they do not touch; with buffers they do); 17:00–14:00 → 400 bad-interval; 06:20–08:00 → 400 bad-interval
with `opens` 06:00 (the shadow would start at 05:40); a missing `from` → 422 naming the field; event `concert` →
400 no-such-event-type; ground `Z` → 404; confirm a slot that has begun → 409 already-started; cancel one that is
over → 409 already-over; confirm a cancelled one → 409 cancelled.

## Conventions

- Every error is `application/problem+json`: `type, title, status, detail` plus the fields the ticket names
  (`clashes_with`, `opens`/`closes`, `errors[]`).
- Ids are opaque strings (booking `BK0001`, ground `A`, event type `league`); database integers never reach the wire
  or the log.
- Timestamps are ISO-8601 UTC with a `Z`. Intervals are half-open `[from, to)`; two intervals clash when
  `from1 < to2 and from2 < to1`, computed on the shadows (interval ± the event type's buffers), never on the bare intervals.
- The clock and the database session are `Depends` dependencies; every rule about time reads the injected clock.

<!-- learntube:start -->
---

[![tests](https://github.com/Oindrila10122005/groundbook-python/actions/workflows/tests.yml/badge.svg)](https://github.com/Oindrila10122005/groundbook-python/actions/workflows/tests.yml)

### Progress

- [x] Ticket 1 · The complex, as a day you can look at
- [x] Ticket 2 · A club asks for a slot
- [x] Ticket 3 · Confirm, cancel, and the hour that has already gone
- [x] Ticket 4 · The refusals, once the shadows are counted
- [x] Ticket 5 · Moving a booking without breaking the day
- [x] Ticket 6 · A planner nobody can erase
- [x] Ticket 7 · One file becomes an app
- [x] Ticket 8 · The rule table, and then the rule changes
- [x] Ticket 9 · It runs on the office machine
- [x] Ticket 10 · It survives being switched off

Built by Oindrila Hazra on [LearnTube Guided Projects](https://guidedprojects.learntube.ai).
<!-- learntube:end -->
