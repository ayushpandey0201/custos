"""SignalEngine ABC — the ONE interface every engine obeys.

Rule: engines never import each other. Cross-engine flow goes through the Trust Engine.
"""

from abc import ABC, abstractmethod

from shared.schemas.evaluation import EvaluationContext
from shared.schemas.signals import SignalResult


class SignalEngine(ABC):
    @abstractmethod
    async def evaluate(self, ctx: EvaluationContext) -> SignalResult:
        ...

