"""FastAPI app factory, middleware stack, routes. [MVP] DATA PLANE — hot path, p99 <= 50ms."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Custos Gateway")
    return app


app = create_app()

