"""Orchestrator: fan-out to engines, gather results, aggregate."""

from shared.schemas.evaluation import EvaluationContext, EvaluationResponse


async def evaluate(ctx: EvaluationContext) -> EvaluationResponse:
    raise NotImplementedError

