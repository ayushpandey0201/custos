"""RiskEngine(SignalEngine): "How DANGEROUS is this situation?" [FUTURE]

Neutral stub until built — always returns a non-vetoing, neutral signal.
"""

from engines.base.engine import SignalEngine
from shared.schemas.evaluation import EvaluationContext
from shared.schemas.signals import SignalResult


class RiskEngine(SignalEngine):
    async def evaluate(self, ctx: EvaluationContext) -> SignalResult:
        return SignalResult(engine="risk", score=1.0, degraded=True)

