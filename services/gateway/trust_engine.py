"""Orchestrator: fan-out to engines, gather results, aggregate.

The only component that knows more than one engine exists. Engines stay
mutually ignorant; everything they would otherwise need to say to each other is
said here, through ``SignalResult``.

Sequence for one request:

    resolve config -> build engines -> fan out concurrently (bounded by a
    per-engine timeout) -> fuse -> decide -> audit -> respond

Fan-out is concurrent, so total engine latency is the slowest engine rather
than the sum. That is what keeps the p99 budget achievable as engines are added:
a fourth signal costs nothing as long as it fits in the same timeout.
"""

from __future__ import annotations

import asyncio
import time

from engines import registry
from engines.base.engine import SignalEngine
from services.gateway import audit
from services.gateway.aggregate import aggregate
from services.gateway.decision import evaluate_decision
from shared.config import defaults
from shared.config.tenant import TenantConfig, load_tenant_config
from shared.schemas.decision import DecisionRecord
from shared.schemas.evaluation import EvaluationContext, EvaluationResponse
from shared.schemas.signals import SignalResult
from shared.telemetry import metrics
from shared.telemetry.logging import get_logger

log = get_logger(__name__)


async def evaluate(
    ctx: EvaluationContext,
    config: TenantConfig | None = None,
    write_audit: bool = True,
) -> EvaluationResponse:
    """Produce a verdict for one request."""
    started = time.perf_counter()
    registry.load_builtin_engines()

    config = config or load_tenant_config(ctx.tenant_id)
    engines = registry.build_engines(config.enabled_engines)

    signals = await _fan_out(engines, ctx)
    fused = aggregate(signals, config.weights)
    outcome = evaluate_decision(fused, config.thresholds, model_known=ctx.model_known)

    latency_ms = (time.perf_counter() - started) * 1000
    signal_map = {s.engine: s for s in signals}

    response = EvaluationResponse(
        decision=outcome.decision,
        trust_score=round(fused.score, 6),
        reasons=outcome.reasons,
        signals=signal_map,
        degraded_engines=fused.degraded_engines,
        trace_id=ctx.trace_id,
        latency_ms=round(latency_ms, 3),
    )

    metrics.record_decision(outcome.decision.value, ctx.tenant_id)
    metrics.record_latency_ms("gateway", latency_ms)

    if write_audit:
        response.audit_id = _write_audit(ctx, response, fused.contributions)

    log.info(
        "decision",
        extra={
            "trace_id": ctx.trace_id,
            "tenant_id": ctx.tenant_id,
            "model_id": ctx.model_id,
            "decision": outcome.decision.value,
            "trust_score": response.trust_score,
            "latency_ms": response.latency_ms,
            "degraded": fused.degraded_engines,
        },
    )
    return response


async def _fan_out(engines: list[SignalEngine], ctx: EvaluationContext) -> list[SignalResult]:
    """Run every engine concurrently under a shared deadline.

    An engine that overruns is cancelled and reported as degraded. One slow
    engine must not spend the whole request's latency budget — the other
    signals are still worth having, and a timeout is information in itself.
    """
    if not engines:
        return []

    timeout_s = defaults.ENGINE_TIMEOUT_MS / 1000

    async def run(engine: SignalEngine) -> SignalResult:
        try:
            return await asyncio.wait_for(engine.evaluate_safely(ctx), timeout=timeout_s)
        except TimeoutError:
            metrics.record_degraded(engine.name)
            return SignalResult.degraded_result(
                engine.name, reason="timeout", timeout_ms=defaults.ENGINE_TIMEOUT_MS
            )

    return list(await asyncio.gather(*(run(e) for e in engines)))


def _write_audit(
    ctx: EvaluationContext, response: EvaluationResponse, contributions: dict[str, float]
) -> str | None:
    """Append the decision to the chain and mirror it into the decision log.

    Failure here is logged but never raised. A decision that was correctly made
    and correctly returned should not turn into a 500 because the audit writer
    had a bad moment — the caller has already acted on the verdict by then.
    """
    record = DecisionRecord(
        decision=response.decision,
        trust_score=response.trust_score,
        tenant_id=ctx.tenant_id,
        model_id=ctx.model_id,
        action=ctx.action,
        trace_id=ctx.trace_id,
        reasons=response.reasons,
        signals={name: s.model_dump() for name, s in response.signals.items()},
        degraded_engines=response.degraded_engines,
    )

    try:
        payload = audit.build_record(record, context={"weights_applied": contributions})
        entry_hash = audit.append_to_chain(payload, ctx.tenant_id)
        _log_decision_row(ctx, response)
        return entry_hash
    except Exception as exc:
        log.error(
            "audit_write_failed",
            extra={"trace_id": ctx.trace_id, "error": f"{type(exc).__name__}: {exc}"},
        )
        return None


def _log_decision_row(ctx: EvaluationContext, response: EvaluationResponse) -> None:
    """Denormalised copy for the dashboard.

    The audit chain is the record of truth but is expensive to query — every
    read has to verify. This table exists so the decisions view is a plain
    indexed SELECT.
    """
    from shared.db.models import DecisionLog
    from shared.db.session import session_scope

    with session_scope() as db:
        db.add(
            DecisionLog(
                tenant_id=ctx.tenant_id,
                model_id=ctx.model_id,
                decision=response.decision.value,
                trust_score=response.trust_score,
                action=ctx.action,
                trace_id=ctx.trace_id,
                reasons=response.reasons,
                signals={name: s.model_dump() for name, s in response.signals.items()},
                latency_ms=response.latency_ms,
            )
        )


def record_features(ctx: EvaluationContext) -> None:
    """Persist the feature vector for the next drift recompute.

    Called off the response path. Best-effort by design: losing one sample from
    a drift window is immaterial, and failing a live decision in order to store
    telemetry would be an absurd trade.
    """
    if not ctx.features:
        return

    from shared.db.models import FeatureSample
    from shared.db.session import session_scope

    try:
        with session_scope() as db:
            db.add(
                FeatureSample(tenant_id=ctx.tenant_id, model_id=ctx.model_id, features=ctx.features)
            )
    except Exception as exc:
        log.warning("feature_sample_dropped", extra={"error": str(exc)})
