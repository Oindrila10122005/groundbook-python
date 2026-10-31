# GroundBook (Python)

[![tests](https://github.com/Oindrila10122005/groundbook-python/actions/workflows/tests.yml/badge.svg)](https://github.com/Oindrila10122005/groundbook-python/actions/workflows/tests.yml)

A municipal sports complex: bookings with setup and teardown buffers that may never overlap.

## Progress

- [x] Ticket 1 · The complex, as a day you can look at
- [x] Ticket 2 · A club asks for a slot
- [x] Ticket 3 · Confirm, cancel, and the hour that has already gone
- [x] Ticket 4 · The refusals, once the shadows are counted
- [x] Ticket 5 · Moving a booking without breaking the day
- [x] Ticket 6 · A planner nobody can erase
- [ ] Ticket 7 · One file becomes an app
- [ ] Ticket 8 · The rule table, and then the rule changes
- [ ] Ticket 9 · It runs on the office machine
- [ ] Ticket 10 · It survives being switched off

## Run it

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest          # the tests
python -m uvicorn groundbook.app:app --port 8080   # the app, on http://127.0.0.1:8080
```

## Built with

Python 3.12 · FastAPI · SQLAlchemy · Pydantic · pytest

---

Built by Oindrila Hazra on [LearnTube Guided Projects](https://guidedprojects.learntube.ai).
