"""FastAPI app factory, middleware stack, routes. [MVP] DATA PLANE — hot path, p99 <= 50ms.

Services contain wiring, not logic. Every decision made in this file is about
transport: authentication, timing, error containment, response shape. The
verdict itself comes entirely from ``trust_engine``.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from engines import registry
from services.gateway import trust_engine
from services.gateway.auth import require_tenant
from shared.config import defaults
from shared.config.tenant import load_tenant_config
from shared.db.registry import is_model_registered
from shared.db.session import ensure_engine, health_check
from shared.schemas.decision import Decision
from shared.schemas.evaluation import (
    EvaluationContext,
    EvaluationRequest,
    EvaluationResponse,
)
from shared.telemetry import metrics
from shared.telemetry.logging import get_logger

log = get_logger(__name__)


class AdmissionGate:
    """Bounded in-flight counter. Refuses instead of queueing.

    No lock: the gateway runs on one event loop and enter/leave never await,
    so the check-and-increment cannot interleave with another request's.
    """

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.in_flight = 0

    def try_enter(self) -> bool:
        if self.in_flight >= self.limit:
            return False
        self.in_flight += 1
        return True

    def leave(self) -> None:
        self.in_flight -= 1


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    ensure_engine()
    registry.load_builtin_engines()
    log.info("gateway_started", extra={"engines": sorted(registry.REGISTRY)})
    yield


def create_app(max_in_flight: int | None = None) -> FastAPI:
    gate = AdmissionGate(max_in_flight or defaults.MAX_IN_FLIGHT)

    app = FastAPI(
        title="Custos Gateway",
        version="0.1.0",
        description="Runtime trust decisions for AI agents and models.",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def timing_and_trace(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Custos-Latency-Ms"] = f"{elapsed_ms:.2f}"
        return response

    @app.post("/v1/evaluate", response_model=EvaluationResponse)
    async def evaluate(
        request: EvaluationRequest,
        background: BackgroundTasks,
        tenant_id: str = Depends(require_tenant),
    ) -> EvaluationResponse:
        """The hot path. One call, one verdict."""
        if not gate.try_enter():
            # Shed, don't queue. The caller learns immediately that no verdict
            # was produced; the SDK then applies the tenant's fail-open or
            # fail-closed policy. A fabricated REVIEW here would flood the human
            # queue with requests nobody evaluated — the overload behaviour this
            # replaces.
            metrics.increment("custos_shed_total", {"tenant": tenant_id})
            return JSONResponse(
                status_code=503,
                content={"detail": "custos at capacity, request not evaluated", "shed": True},
                headers={"Retry-After": "1"},
            )
        try:
            return await _evaluate_admitted(request, background, tenant_id)
        finally:
            gate.leave()

    async def _evaluate_admitted(
        request: EvaluationRequest, background: BackgroundTasks, tenant_id: str
    ) -> EvaluationResponse | JSONResponse:
        # Off-thread: a cache miss here reads the database, and nothing on the
        # hot path may block the event loop (see AdmissionGate).
        model_known = await asyncio.to_thread(is_model_registered, tenant_id, request.model_id)
        ctx = EvaluationContext.from_request(request, tenant_id=tenant_id, model_known=model_known)

        try:
            response = await trust_engine.evaluate(ctx)
        except Exception as exc:
            # Fail-open (ADR 0001): if Custos cannot reach a verdict, the caller
            # still gets to make progress. The failure is loud in logs and
            # metrics, never silent, and the response says plainly that the
            # ALLOW was a fallback rather than a judgement.
            log.error(
                "evaluate_failed_open",
                extra={"trace_id": ctx.trace_id, "error": f"{type(exc).__name__}: {exc}"},
            )
            metrics.increment("custos_fail_open_total", {"tenant": tenant_id})
            config = load_tenant_config(tenant_id)
            if not config.fail_open:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "custos unavailable and tenant is configured fail-closed"},
                )
            return EvaluationResponse(
                decision=Decision.ALLOW,
                trust_score=1.0,
                reasons=["custos failed open: evaluation error, caller allowed to proceed"],
                degraded_engines=["*"],
                trace_id=ctx.trace_id,
            )

        # Feature capture feeds the next drift recompute and must never be on
        # the response path — the caller is waiting on a decision, not on us
        # writing telemetry.
        background.add_task(trust_engine.record_features, ctx)
        return response

    @app.get("/health")
    async def health() -> dict:
        db_ok = health_check()
        return {
            "status": "ok" if db_ok else "degraded",
            "database": "up" if db_ok else "down",
            "engines": sorted(registry.REGISTRY),
            "fail_open": defaults.FAIL_OPEN,
        }

    @app.get("/metrics", response_class=PlainTextResponse)
    async def prometheus_metrics() -> Response:
        return PlainTextResponse(metrics.render_prometheus())

    @app.get("/metrics.json")
    async def json_metrics() -> dict:
        return {**metrics.snapshot(), "in_flight": gate.in_flight, "max_in_flight": gate.limit}

    return app


app = create_app()
