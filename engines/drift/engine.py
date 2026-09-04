"""DriftEngine(SignalEngine): reads precomputed severity -> SignalResult. [MVP] THE MOAT.

See docs/adr/0002-precomputed-drift.md and docs/adr/0004-degraded-drift-default.md.

This engine does no statistics. Every PSI and KS computation happens offline in
``engines/drift/worker.py``; on the hot path this is one cached read and a
subtraction. That is the whole point of ADR 0002 — the expensive part of the
drift signal is paid for on a schedule, not per request.
"""

from __future__ import annotations

import asyncio

from engines.base.engine import SignalEngine
from engines.drift import severity as severity_mod
from shared.cache import get_cache
from shared.schemas.evaluation import EvaluationContext
from shared.schemas.signals import SignalResult
from shared.timeutil import iso_utc

# Severity changes at most once per recompute interval, so a short TTL costs
# nothing in freshness and removes a database round-trip from the hot path.
_CACHE_TTL_S = 15


def _cache_key(tenant_id: str, model_id: str) -> str:
    return f"custos:drift:{tenant_id}:{model_id}"


def latest_snapshot(tenant_id: str, model_id: str) -> dict | None:
    """Most recent drift snapshot for a model, or None if never computed."""
    cache = get_cache()
    key = _cache_key(tenant_id, model_id)
    cached = cache.get(key)
    if cached is not None:
        return cached or None

    from sqlalchemy import select

    from shared.db.models import DriftSnapshot
    from shared.db.session import session_scope

    with session_scope() as db:
        row = db.execute(
            select(DriftSnapshot)
            .where(
                DriftSnapshot.tenant_id == tenant_id,
                DriftSnapshot.model_id == model_id,
            )
            .order_by(DriftSnapshot.computed_at.desc(), DriftSnapshot.id.desc())
            .limit(1)
        ).scalar_one_or_none()

        snapshot = (
            None
            if row is None
            else {
                "severity": row.severity,
                "per_feature": row.per_feature or {},
                "sample_size": row.sample_size,
                "computed_at": iso_utc(row.computed_at),
            }
        )

    # Cache the miss too ({} is falsy but not None), so a model that has never
    # been scored does not hit the database on every single request.
    cache.set(key, snapshot or {}, _CACHE_TTL_S)
    return snapshot


def invalidate(tenant_id: str, model_id: str) -> None:
    """Evict after the worker writes a new snapshot."""
    get_cache().delete(_cache_key(tenant_id, model_id))


class DriftEngine(SignalEngine):
    """Trust = 1 − drift severity."""

    name = "drift"

    async def evaluate(self, ctx: EvaluationContext) -> SignalResult:
        # Off-thread: on a cache miss this touches the database, and blocking
        # the event loop would make the fan-out timeout unenforceable.
        snapshot = await asyncio.to_thread(latest_snapshot, ctx.tenant_id, ctx.model_id)

        if snapshot is None:
            # No baseline, or the worker has not run yet. Per ADR 0004 this is
            # degraded trust — visible in aggregation and audit — rather than a
            # confident 1.0 (silently unsafe) or a BLOCK (blocks every new model
            # on its first request).
            return SignalResult.degraded_result(
                self.name, reason="no_drift_snapshot", model_id=ctx.model_id
            )

        drift_severity = float(snapshot["severity"])
        per_feature = snapshot.get("per_feature", {})
        contributors = severity_mod.top_contributors(per_feature)

        return SignalResult(
            engine=self.name,
            score=max(0.0, min(1.0, 1.0 - drift_severity)),
            degraded=False,
            detail={
                "severity": round(drift_severity, 4),
                "band": severity_mod.severity_band(drift_severity),
                "top_features": [
                    {"feature": name, "severity": round(value, 4)} for name, value in contributors
                ],
                "sample_size": snapshot.get("sample_size", 0),
                "computed_at": snapshot.get("computed_at"),
            },
        )
