"""PolicyEngine(SignalEngine): "Is this action ALLOWED?" [MVP-lite]"""

from engines.base.engine import SignalEngine
from shared.schemas.evaluation import EvaluationContext
from shared.schemas.signals import SignalResult


class PolicyEngine(SignalEngine):
    async def evaluate(self, ctx: EvaluationContext) -> SignalResult:
        raise NotImplementedError

