"""FastAPI app factory + routes. [MVP] CONTROL PLANE — cold, never on the hot path."""

from fastapi import FastAPI

from services.control import (
    routes_audit,
    routes_config,
    routes_drift,
    routes_models,
)


def create_app() -> FastAPI:
    app = FastAPI(title="Custos Control Plane")
    app.include_router(routes_models.router)
    app.include_router(routes_config.router)
    app.include_router(routes_audit.router)
    app.include_router(routes_drift.router)
    return app


app = create_app()

