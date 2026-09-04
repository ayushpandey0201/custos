"""DecisionEngine: thresholds + vetoes -> ALLOW / BLOCK / REVIEW.

Unknown model_id routes to REVIEW — see docs/adr/0005-unknown-model-review.md.

The decision matrix (docs/architecture.md §8.6) is implemented as a single
ordered cascade. Order is the specification, so it is written once, here, and
tested row by row in tests/unit/test_decision_table.py.

    #  Condition                          Decision   Why
    1  any veto                           BLOCK      hard stop, unconditional
    2  trust < block threshold            BLOCK      fused evidence is damning
    3  model_id not registered            REVIEW     ADR 0005
    4  every engine degraded              REVIEW     Custos has no signal at all
    5  trust < review threshold           REVIEW     ambiguous
    6  otherwise                          ALLOW

Rule 2 precedes rule 3 deliberately: an unregistered model whose signals are
*already* damning should be blocked, not merely flagged.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.gateway.aggregate import AggregateResult
from shared.schemas.decision import Decision


@dataclass
class DecisionOutcome:
    decision: Decision
    reasons: list[str]


def decide(
    trust_score: float,
    thresholds: dict[str, float],
    vetoed: bool = False,
    model_known: bool = True,
    all_degraded: bool = False,
) -> Decision:
    """Apply the decision matrix. See :func:`decide_with_reasons` for the why."""
    return decide_with_reasons(trust_score, thresholds, vetoed, model_known, all_degraded).decision


def decide_with_reasons(
    trust_score: float,
    thresholds: dict[str, float],
    vetoed: bool = False,
    model_known: bool = True,
    all_degraded: bool = False,
) -> DecisionOutcome:
    """The decision plus the ordered reasons behind it.

    Reasons are part of the product, not debug output: a BLOCK a caller cannot
    explain to a customer is a BLOCK they will switch off.
    """
    block_at = thresholds.get("block", 0.3)
    review_at = thresholds.get("review", 0.6)

    if vetoed:
        return DecisionOutcome(Decision.BLOCK, ["policy veto raised by an engine"])

    if trust_score < block_at:
        return DecisionOutcome(
            Decision.BLOCK,
            [f"trust score {trust_score:.2f} below block threshold {block_at:.2f}"],
        )

    if not model_known:
        return DecisionOutcome(
            Decision.REVIEW, ["model_id is not registered with Custos (ADR 0005)"]
        )

    if all_degraded:
        return DecisionOutcome(
            Decision.REVIEW, ["no engine produced a confident signal; trust is unestablished"]
        )

    if trust_score < review_at:
        return DecisionOutcome(
            Decision.REVIEW,
            [f"trust score {trust_score:.2f} below review threshold {review_at:.2f}"],
        )

    return DecisionOutcome(
        Decision.ALLOW, [f"trust score {trust_score:.2f} at or above {review_at:.2f}"]
    )


def evaluate_decision(
    result: AggregateResult, thresholds: dict[str, float], model_known: bool = True
) -> DecisionOutcome:
    """Decide from an :class:`AggregateResult`, enriching the reasons with evidence."""
    outcome = decide_with_reasons(
        trust_score=result.score,
        thresholds=thresholds,
        vetoed=result.vetoed,
        model_known=model_known,
        all_degraded=result.all_degraded,
    )

    reasons = list(outcome.reasons)
    for veto in result.vetoes:
        reasons.append(f"{veto.engine}: {veto.reason}")
    if result.degraded_engines and not result.all_degraded:
        reasons.append(
            f"degraded engines excluded from fusion: {', '.join(result.degraded_engines)}"
        )

    return DecisionOutcome(outcome.decision, reasons)
