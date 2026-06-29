"""FastAPI application entrypoint.

Serves the JSON API under /api and the static dashboard at /. Starts the
background scan scheduler on startup and tears it down cleanly on shutdown.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.http_client import close_client
from app.routers import catalysts, flow, system
from app.scheduler import shutdown_scheduler, start_scheduler

_STATIC_DIR = Path(__file__).parent / "static"


def _configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()
        await close_client()


def create_app() -> FastAPI:
    app = FastAPI(
        title="FlowScope",
        description="Free multi-source options-flow & catalyst dashboard",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(flow.router)
    app.include_router(catalysts.router)
    app.include_router(system.router)

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    app.mount("/", StaticFiles(directory=_STATIC_DIR), name="static")
    return app


app = create_app()
