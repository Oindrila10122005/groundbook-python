"""Routers per resource, docs that list every documented error with an example and nothing a call cannot
answer, one set of handlers for every error -- the refusals, the framework's own 404/405 and the unexpected."""
import ast
import json
import logging
import subprocess
import sys
from pathlib import Path

from groundbook.handlers import PROBLEM

PKG = Path(__file__).resolve().parent.parent / "groundbook"
# every 4xx type
ERRORS = {"/errors/validation", "/errors/bad-interval", "/errors/no-such-ground", "/errors/no-such-booking", "/errors/overlap",
          "/errors/already-started", "/errors/already-over", "/errors/cancelled"}
# and every answer each operation can give, and nothing else (no stock 422 where there is no body; 500 everywhere)
ANSWERS = {
    ("get", "/venues/{venue}/grounds"): {"200", "404", "500"},
    ("get", "/venues/{venue}/event-types"): {"200", "404", "500"},
    ("get", "/venues/{venue}/grounds/{ground}/day"): {"200", "400", "404", "500"},
    ("post", "/bookings"): {"201", "400", "404", "409", "422", "500"},
    ("get", "/bookings/{booking_id}"): {"200", "404", "500"},
    ("post", "/bookings/{booking_id}/confirm"): {"200", "404", "409", "500"},
    ("post", "/bookings/{booking_id}/cancel"): {"200", "404", "409", "500"},
    ("post", "/bookings/{booking_id}/move"): {"200", "400", "404", "409", "422", "500"},
    ("get", "/settings"): {"200", "500"},    ("get", "/healthz"): {"200", "500"},
}


def examples(op, status):
    content = op["responses"][status]["content"][PROBLEM]
    return {ex["type"]: ex for ex in ([content["example"]] if "example" in content else [v["value"] for v in content["examples"].values()])}


def test_docs_render_and_list_every_endpoint_with_a_summary_and_a_tag(client):
    assert client.get("/docs").status_code == 200
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    assert set(paths) == {"/venues/{venue}/grounds", "/venues/{venue}/event-types", "/venues/{venue}/grounds/{ground}/day", "/bookings",
                          "/bookings/{booking_id}", "/bookings/{booking_id}/confirm", "/bookings/{booking_id}/cancel", "/bookings/{booking_id}/move",
                          "/settings"}
    assert {t["name"] for t in spec["tags"]} == {"grounds", "bookings", "moves", "settings" ,"/settings", "/healthz"}
    for path, ops in paths.items():
        for op in ops.values():
            assert op.get("summary") and len(op.get("tags", [])) == 1, path
    tags = {(m, p): op["tags"][0] for p, ops in paths.items() for m, op in ops.items()}
    assert tags == {("get", "/venues/{venue}/grounds"): "grounds", ("get", "/venues/{venue}/event-types"): "grounds",
                    ("get", "/venues/{venue}/grounds/{ground}/day"): "grounds", ("post", "/bookings"): "bookings",
                    ("get", "/bookings/{booking_id}"): "bookings", ("post", "/bookings/{booking_id}/confirm"): "bookings",
                    ("post", "/bookings/{booking_id}/cancel"): "bookings", ("post", "/bookings/{booking_id}/move"): "moves",
                    ("get", "/settings"): "settings" ,                    ("get", "/settings"): "settings", ("get", "/healthz"): "settings"}


def test_every_refusal_is_documented_with_a_problem_example(client):
    spec = client.get("/openapi.json").json()
    post = spec["paths"]["/bookings"]["post"]
    assert set(examples(post, "409")) == {"/errors/overlap"} and examples(post, "409")["/errors/overlap"]["clashes_with"][0]["booking_id"]
    assert set(examples(post, "400")) == {"/errors/bad-interval", "/errors/no-such-event-type"} and examples(post, "400")["/errors/bad-interval"]["opens"] == "06:00"
    assert set(examples(post, "404")) == {"/errors/no-such-ground"}
    assert examples(post, "422")["/errors/validation"]["errors"][0]["field"] == "from"
    move = spec["paths"]["/bookings/{booking_id}/move"]["post"]
    assert set(examples(move, "409")) == {"/errors/overlap", "/errors/already-started", "/errors/cancelled"}
    assert set(examples(move, "400")) == {"/errors/bad-interval"} and set(examples(move, "404")) == {"/errors/no-such-booking"}
    assert set(examples(move, "422")) == {"/errors/validation"}
    confirm = spec["paths"]["/bookings/{booking_id}/confirm"]["post"]
    assert set(examples(confirm, "409")) == {"/errors/already-started", "/errors/cancelled", "/errors/already-confirmed", "/errors/overlap"}
    assert set(examples(confirm, "404")) == {"/errors/no-such-booking"}
    cancel = spec["paths"]["/bookings/{booking_id}/cancel"]["post"]
    assert set(examples(cancel, "409")) == {"/errors/already-over", "/errors/already-cancelled"} and set(examples(cancel, "404")) == {"/errors/no-such-booking"}
    day = spec["paths"]["/venues/{venue}/grounds/{ground}/day"]["get"]
    assert set(examples(day, "400")) == {"/errors/validation"} and set(examples(day, "404")) == {"/errors/no-such-ground", "/errors/no-such-venue"}
    assert set(examples(spec["paths"]["/bookings/{booking_id}"]["get"], "404")) == {"/errors/no-such-booking"}
    for path in ("/venues/{venue}/grounds", "/venues/{venue}/event-types"):
        assert set(examples(spec["paths"][path]["get"], "404")) == {"/errors/no-such-venue"}


def test_no_operation_documents_an_answer_it_cannot_send(client):
    spec = client.get("/openapi.json").json()
    got = {(m, p): set(op["responses"]) for p, ops in spec["paths"].items() for m, op in ops.items()}
    assert got == ANSWERS
    for (m, p), op in ((k, spec["paths"][k[1]][k[0]]) for k in ANSWERS):
        for status, answer in op["responses"].items():
            if status.startswith("2"):
                continue
            assert set(answer["content"]) == {PROBLEM}, (m, p, status, "an error is problem+json only, never FastAPI's stock schema")
            for ex in examples(op, status).values():
                assert {"type", "title", "status", "detail"} <= set(ex) and ex["status"] == int(status), (m, p, status, ex)
        assert examples(op, "500") == {"/errors/internal": {"type": "/errors/internal", "title": "Something went wrong", "status": 500,
                                                            "detail": "The request could not be completed"}}
    schemas = spec["components"]["schemas"]
    assert "HTTPValidationError" not in schemas and "ValidationError" not in schemas
    assert "HTTPValidationError" not in json.dumps(spec)


def test_the_201_documents_its_location_header(client):
    created = client.get("/openapi.json").json()["paths"]["/bookings"]["post"]["responses"]["201"]
    assert created["headers"]["Location"]["schema"] == {"type": "string"} and "/bookings/" in created["headers"]["Location"]["description"]
    assert created["content"]["application/json"]["schema"]["$ref"].endswith("/BookingCreatedOut")


def test_every_4xx_in_the_shared_error_list_is_on_an_endpoint(client):
    spec = client.get("/openapi.json").json()
    documented = set()
    for ops in spec["paths"].values():
        for op in ops.values():
            for status in op["responses"]:
                if status.startswith("4"):
                    documented |= set(examples(op, status))
    assert ERRORS <= documented, ERRORS - documented


def test_the_type_values_are_frozen():
    src = (PKG / "errors.py").read_text(encoding="utf-8")
    types = set(__import__("re").findall(r'"(/errors/[a-z-]+)"', src))
    assert types == ERRORS | {"/errors/no-such-venue", "/errors/no-such-event-type", "/errors/already-confirmed", "/errors/already-cancelled",
                              "/errors/internal", "/errors/domain", "/errors/not-found", "/errors/method-not-allowed", "/errors/http"}


def test_unexpected_exception_is_a_generic_problem_and_its_path_is_logged(app, client, caplog):
    @app.get("/boom", include_in_schema=False)
    def boom():
        raise RuntimeError("secret detail")

    caplog.set_level(logging.INFO)
    r = client.get("/boom")
    assert r.status_code == 500 and r.headers["content-type"].startswith(PROBLEM)
    assert r.json() == {"type": "/errors/internal", "title": "Something went wrong", "status": 500, "detail": "The request could not be completed"}
    assert "secret detail" not in r.text and "Traceback" not in r.text
    lines = [rec.getMessage() for rec in caplog.records]
    assert "unhandled error method=GET path=/boom" in lines, "the exception is logged with its path"
    assert "request method=GET path=/boom status=500" in lines, "and the request still gets its one line"
    assert not any("request_id" in line for line in lines)


def test_an_unknown_path_and_a_wrong_method_are_problem_json(client):
    r = client.get("/nope")
    assert r.status_code == 404 and r.headers["content-type"].startswith(PROBLEM)
    assert r.json() == {"type": "/errors/not-found", "title": "No such resource", "status": 404, "detail": "Nothing is served at /nope"}
    r = client.delete("/venues/deccan/grounds")
    assert r.status_code == 405 and r.headers["content-type"].startswith(PROBLEM) and r.headers["allow"] == "GET"
    assert r.json()["type"] == "/errors/method-not-allowed" and r.json()["title"] == "Method not allowed" and r.json()["status"] == 405
    assert client.get("/static/nothing-here.js").json()["type"] == "/errors/not-found"


def test_services_and_rules_import_nothing_from_fastapi():
    for path in list(( PKG / "services").glob("*.py")) + [PKG / n for n in ("models.py", "clock.py", "ids.py", "errors.py", "settings.py", "schemas.py")]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = node.module if isinstance(node, ast.ImportFrom) else node.names[0].name
                assert not (mod or "").startswith(("fastapi", "starlette")), path.name


def test_services_and_rules_do_not_pull_in_fastapi_even_indirectly():
    modules = [f"groundbook.services.{p.stem}" for p in sorted((PKG / "services").glob("*.py")) if p.stem != "__init__"]
    modules += ["groundbook.errors", "groundbook.clock", "groundbook.ids", "groundbook.models", "groundbook.settings", "groundbook.schemas"]
    code = ("import importlib, sys\n"
            f"for m in {modules!r}: importlib.import_module(m)\n"
            "print(sorted(k for k in sys.modules if k.split('.')[0] in ('fastapi', 'starlette')))")
    out = subprocess.run([sys.executable, "-c", code], cwd=PKG.parent, capture_output=True, text=True, check=True,
                         env={**__import__("os").environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert out.stdout.strip() == "[]", out.stdout


def test_one_router_per_resource_mounted_from_one_app():
    assert {p.stem for p in (PKG / "routers").glob("*.py")} == {"__init__", "grounds", "bookings", "moves", "settings"}
    app_src = (PKG / "app.py").read_text(encoding="utf-8")
    assert app_src.count("include_router") == 1 and "for r in (grounds.router, bookings.router, moves.router, settings_router.router)" in app_src
    for name in ("grounds", "bookings", "moves"):
        assert "APIRouter(" in (PKG / "routers" / f"{name}.py").read_text(encoding="utf-8")