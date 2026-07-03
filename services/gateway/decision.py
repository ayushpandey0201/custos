"""DecisionEngine: thresholds + vetoes -> ALLOW / BLOCK / REVIEW.

Unknown model_id routes to REVIEW — see docs/adr/0005-unknown-model-review.md.
"""

from shared.schemas.decision import Decision


def decide(trust_score: float, thresholds: dict[str, float], vetoed: bool) -> Decision:
    raise NotImplementedError

