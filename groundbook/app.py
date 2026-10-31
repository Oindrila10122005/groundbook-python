"""one set of error handlers, and an OpenAPI document that
lists exactly the answers each call can give."""
import copy
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import init_db, make_engine, make_sessionmaker
from .handlers import INTERNAL_RESPONSE, PROBLEM, VALIDATION_RESPONSE, install_handlers
from .routers import bookings, grounds, moves
from .routers import settings as settings_router
from .services.seed import seed
from .settings import Settings

STATIC = Path(__file__).parent / "static"
TAGS = [
    {"name": "grounds", "description": "The complex -- four grounds, their hours, six event types with buffers -- and one ground's day as blocks with shadows"},
    {"name": "bookings", "description": "A club asks for a slot; the office confirms or cancels it"},
    {"name": "moves", "description": "A booking moves, the whole new interval re-checked with its buffers"},
    {"name": "settings", "description": "Rules in force, health"},
]


def honest_openapi(app: FastAPI):
    """The default schema, then per operation: FastAPI's stock 422 goes where there is no body (a query or path
    parameter that fails is the 400 validation problem, documented on the route); where there is a body the 422 is
    the app's own problem+json; every operation documents the generic 500. Unreferenced stock schemas are dropped."""
    def openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes,
                             tags=app.openapi_tags)
        for ops in schema["paths"].values():
            for op in ops.values():
                answers = op["responses"]
                if "requestBody" in op:
                    answers.update(copy.deepcopy({str(k): v for k, v in VALIDATION_RESPONSE.items()}))
                elif "422" in answers and PROBLEM not in answers["422"].get("content", {}):
                    del answers["422"]
                answers.update(copy.deepcopy({str(k): v for k, v in INTERNAL_RESPONSE.items()}))
        components = schema.get("components", {}).get("schemas", {})
        for name in ("HTTPValidationError", "ValidationError"):
            others = {k: v for k, v in components.items() if k != name}
            if name in components and f"#/components/schemas/{name}" not in json.dumps([schema["paths"], others]):
                del components[name]
        app.openapi_schema = schema
        return schema
    return openapi


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(engine)
        with app.state.sessionmaker() as session:
            seed(session, settings.seed_dir)
        yield
        engine.dispose()

    app = FastAPI(title="GroundBook", version="0.1.0", lifespan=lifespan, openapi_tags=TAGS,
                  description="A municipal sports complex: bookings with setup and teardown buffers that may never overlap.")
    app.state.settings = settings
    app.state.sessionmaker = make_sessionmaker(engine)

    install_handlers(app)
    for r in (grounds.router, bookings.router, moves.router, settings_router.router):
        app.include_router(r)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    app.openapi = honest_openapi(app)
    return app


app = create_app()