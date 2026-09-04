"""FastAPI app factory + routes. [MVP] CONTROL PLANE — cold, never on the hot path.

Registration, configuration, drift history and audit retrieval. Nothing here is
in the request path of a live decision, which is why these endpoints are free to
do slow, correct things — validating a rule grammar, verifying a whole hash
chain — that would be unacceptable in the gateway.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.control import (
    routes_audit,
    routes_config,
    routes_drift,
    routes_models,
    routes_tenants,
)
from shared.db.session import ensure_engine, health_check
from shared.telemetry.logging import get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    ensure_engine()
    log.info("control_plane_started")
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Custos Control Plane",
        version="0.1.0",
        description="Model registration, tenant policy, drift history and audit evidence.",
        lifespan=lifespan,
    )

    # The dashboard is served from a different origin in development.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(routes_tenants.router)
    app.include_router(routes_models.router)
    app.include_router(routes_drift.router)
    app.include_router(routes_config.router)
    app.include_router(routes_audit.router)

    @app.get("/health")
    def health() -> dict:
        db_ok = health_check()
        return {"status": "ok" if db_ok else "degraded", "database": "up" if db_ok else "down"}

    return app


app = create_app()
