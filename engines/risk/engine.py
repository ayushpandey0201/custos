"""RiskEngine(SignalEngine): "How DANGEROUS is this situation?" [FUTURE]

Neutral stub until built — always returns a non-vetoing, degraded signal.

The seam exists so that adding contextual risk (transaction velocity, anomaly
scores, blast radius of the action) is a new file rather than a refactor.
Returning ``degraded`` rather than a confident 1.0 is deliberate: an unbuilt
engine must not silently contribute trust it has not earned. Aggregation
excludes it and the audit record shows *why* it was excluded.
"""

from __future__ import annotations

from engines.base.engine import SignalEngine
from shared.schemas.evaluation import EvaluationContext
from shared.schemas.signals import SignalResult


class RiskEngine(SignalEngine):
    name = "risk"

    async def evaluate(self, ctx: EvaluationContext) -> SignalResult:
        return SignalResult.degraded_result(self.name, reason="engine_not_implemented")
