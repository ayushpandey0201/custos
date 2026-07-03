"""DriftEngine(SignalEngine): reads precomputed severity -> SignalResult. [MVP] THE MOAT.

See docs/adr/0002-precomputed-drift.md and docs/adr/0004-degraded-drift-default.md.
"""

from engines.base.engine import SignalEngine
from shared.schemas.evaluation import EvaluationContext
from shared.schemas.signals import SignalResult


class DriftEngine(SignalEngine):
    async def evaluate(self, ctx: EvaluationContext) -> SignalResult:
        raise NotImplementedError

