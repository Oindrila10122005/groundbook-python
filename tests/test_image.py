"""The image recipe and the health call. The build itself and the calls from another host are run by hand
with docker; what can be checked in-process is here."""
"""What can be checked without Docker: health, the image recipe and the lock file."""
import re

from tests.conftest import ROOT, V


def test_health_is_up(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert len(client.get(f"{V}/grounds").json()["grounds"]) == 4, "the list the gate tablet reads first"



def test_dockerfile_matches_the_contract_and_takes_host_and_port_from_the_environment():
    lines = (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines()
    text = "\n".join(lines)
    assert "FROM python:3.12-slim" in lines and "RUN pip install --no-cache-dir -r requirements.lock" in lines
    assert "ENV HOST=0.0.0.0 \\" in lines and "    PORT=8080 \\" in lines, "the defaults"
    assert "DATABASE_URL" not in text, "the env-file carries the database; nothing else is baked in"
    assert 'VOLUME ["/data"]' in lines and "EXPOSE 8080" in lines
    cmd = [line for line in lines if line.startswith("CMD")]
    assert cmd == ['CMD ["sh", "-c", "exec uvicorn groundbook.app:app --host \\"$HOST\\" --port \\"$PORT\\""]'], cmd
    assert "COPY groundbook ./groundbook" in lines and "COPY seed ./seed" in lines and not any(line.startswith("COPY . ") for line in lines)


def test_the_lock_pins_every_package_the_image_installs():
    lock = [line for line in (ROOT / "requirements.lock").read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
    assert all(re.fullmatch(r"[A-Za-z0-9_.-]+==[0-9][\w.]*", line) for line in lock), lock
    names = {line.split("==")[0].lower() for line in lock}
    assert {"fastapi", "uvicorn", "sqlalchemy", "pydantic", "pydantic-settings", "starlette", "pydantic-core", "anyio", "h11", "click"} <= names
    assert len(lock) == 17
    top = (ROOT / "requirements.txt").read_text(encoding="utf-8").split()
    assert top == ["fastapi", "uvicorn", "sqlalchemy", "pydantic", "pydantic-settings"]