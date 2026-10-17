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
    5  an input is quarantined            REVIEW     a human approved a hold (below)
    6  drift in the significant band      REVIEW     drift floor (below)
    7  trust < review threshold           REVIEW     ambiguous
    8  otherwise                          ALLOW

Rule 2 precedes rule 3 deliberately: an unregistered model whose signals are
*already* damning should be blocked, not merely flagged.

Rule 5 exists because fusion is an average, and averages can be outvoted.
While the risk engine was a stub it was always excluded, drift carried 0.5/0.8
of the weight, and a significantly drifted model could never reach ALLOW — by
arithmetic accident. The day risk became a live signal, drift's share fell to
half, and a model at severity 0.8 could be auto-approved whenever policy and
risk were both clean. That property is too important to depend on the weights,
so it is stated here instead: a model that far from its baseline is never
auto-approved, however reassuring the other signals are. It can still be
BLOCKed by rules 1-2; it is only kept out of ALLOW.

Rule 5 is the only rule a person switches on. When self-healing diagnoses a
broken input feed (services/healing), it proposes quarantining that input, and
once someone approves, every decision for that model is held for review until
the feed is repaired and the release is approved too. A model scoring on a
dead input is not making the decision it was validated to make, however normal
its trust score looks. Like the drift floor, it never softens a BLOCK.
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
    drift_significant: bool = False,
    quarantined: dict[str, str] | None = None,
) -> Decision:
    """Apply the decision matrix. See :func:`decide_with_reasons` for the why."""
    return decide_with_reasons(
        trust_score, thresholds, vetoed, model_known, all_degraded, drift_significant, quarantined
    ).decision


def decide_with_reasons(
    trust_score: float,
    thresholds: dict[str, float],
    vetoed: bool = False,
    model_known: bool = True,
    all_degraded: bool = False,
    drift_significant: bool = False,
    quarantined: dict[str, str] | None = None,
) -> DecisionOutcome:
    """The decision plus the ordered reasons behind it.

    ``quarantined`` maps each held input to the reason it is held.

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

    if quarantined:
        return DecisionOutcome(
            Decision.REVIEW,
            [
                f"input {name!r} is quarantined: {why}"
                for name, why in sorted(quarantined.items())
            ],
        )

    if drift_significant:
        return DecisionOutcome(
            Decision.REVIEW,
            [
                "model drift is in the significant band; a model this far from its "
                "baseline is not auto-approved regardless of other signals"
            ],
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
    result: AggregateResult,
    thresholds: dict[str, float],
    model_known: bool = True,
    drift_significant: bool = False,
    quarantined: dict[str, str] | None = None,
) -> DecisionOutcome:
    """Decide from an :class:`AggregateResult`, enriching the reasons with evidence."""
    outcome = decide_with_reasons(
        trust_score=result.score,
        thresholds=thresholds,
        vetoed=result.vetoed,
        model_known=model_known,
        all_degraded=result.all_degraded,
        drift_significant=drift_significant,
        quarantined=quarantined,
    )

    reasons = list(outcome.reasons)
    for veto in result.vetoes:
        reasons.append(f"{veto.engine}: {veto.reason}")
    if result.degraded_engines and not result.all_degraded:
        reasons.append(
            f"degraded engines excluded from fusion: {', '.join(result.degraded_engines)}"
        )

    return DecisionOutcome(outcome.decision, reasons)
