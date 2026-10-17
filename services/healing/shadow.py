"""Shadow-test a repair against the decisions the model actually made.

Every decision's engine signals are stored with it (DecisionLog.signals), so a
proposed repair can be replayed against real recent traffic without touching
production: rebuild each request's signals, apply the repair's effect, and run
the *same* fusion and decision cascade the gateway runs. What a reviewer sees
is "this repair would have changed 212 of the last 500 verdicts, all
ALLOW → REVIEW" — measured, not estimated.

Replay is exact for anything the repair changes in Custos itself (a hold, a new
drift reading). It cannot say whether the *model's* answers would improve —
that needs outcomes Custos does not have at decision time, and the shadow
report says so rather than implying otherwise.
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy import select

from engines.drift.severity import severity_band
from services.gateway.aggregate import aggregate
from services.gateway.decision import evaluate_decision
from shared.config.tenant import load_tenant_config
from shared.db.models import DecisionLog
from shared.db.session import session_scope
from shared.schemas.signals import SignalResult

REPLAY_LIMIT = 500


def replay(
    tenant_id: str,
    model_id: str,
    *,
    quarantined: dict[str, str] | None = None,
    drift_severity: float | None = None,
    limit: int = REPLAY_LIMIT,
) -> dict:
    """Re-decide the model's most recent decisions under a repair.

    Args:
        quarantined: the holds that would be in force after the repair.
        drift_severity: the drift reading the repair would produce, if it
            changes one. None keeps each decision's recorded drift signal.

    Returns:
        ``{"replayed", "changed", "transitions": {"ALLOW→REVIEW": n}, "examples"}``
    """
    config = load_tenant_config(tenant_id)
    with session_scope() as db:
        rows = list(
            db.execute(
                select(DecisionLog)
                .where(DecisionLog.tenant_id == tenant_id, DecisionLog.model_id == model_id)
                .order_by(DecisionLog.id.desc())
                .limit(limit)
            ).scalars()
        )

    transitions: Counter[str] = Counter()
    examples: list[dict] = []
    replayed = 0
    for row in rows:
        # Decisions made before the model was registered were routed by a rule
        # (ADR 0005) the repair has nothing to do with.
        if any("not registered" in reason for reason in row.reasons or []):
            continue
        signals = [SignalResult(**s) for s in (row.signals or {}).values()]
        if drift_severity is not None:
            signals = [_with_drift(s, drift_severity) for s in signals]

        fused = aggregate(signals, config.weights)
        drift = next((s for s in signals if s.engine == "drift" and not s.degraded), None)
        outcome = evaluate_decision(
            fused,
            config.thresholds,
            drift_significant=drift is not None and drift.detail.get("band") == "significant",
            quarantined=quarantined or None,
        )
        replayed += 1
        after = outcome.decision.value
        if after != row.decision:
            transitions[f"{row.decision}→{after}"] += 1
            if len(examples) < 3:
                examples.append({"trace_id": row.trace_id, "from": row.decision, "to": after})

    return {
        "replayed": replayed,
        "changed": sum(transitions.values()),
        "transitions": dict(transitions),
        "examples": examples,
    }


def _with_drift(signal: SignalResult, severity: float) -> SignalResult:
    if signal.engine != "drift":
        return signal
    return SignalResult(
        engine="drift",
        score=max(0.0, min(1.0, 1.0 - severity)),
        degraded=False,
        detail={**signal.detail, "severity": round(severity, 4), "band": severity_band(severity)},
    )
