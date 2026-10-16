"""Review strategies under comparison. Fixed by PROTOCOL.md before any real-data run.

Each strategy turns per-decision signals into a review priority: higher means
"show this one to a human first". Every signal it may use is causal — the model
and percentile scales come from training data, and drift severity is the
*previous* window's — so no strategy can see the outcome it is trying to catch.

`random` is deliberately absent from the table: its expected precision is the
base default rate exactly, so it is computed, not sampled.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from experiments.gating.stats import ECDF


@dataclass(frozen=True)
class Signals:
    risk: list[float]  # model's predicted default probability
    novelty: list[float]  # Mahalanobis distance from the training data
    severity: list[float]  # lagged population drift severity of the decision's window, 0–1
    risk_scale: ECDF  # training-set distribution of risk
    novelty_scale: ECDF  # training-set distribution of novelty


def model_risk(s: Signals) -> list[float]:
    return list(s.risk)


def low_confidence(s: Signals) -> list[float]:
    """Selective prediction's standard baseline: least confident first."""
    return [-abs(p - 0.5) for p in s.risk]


def population_drift(s: Signals) -> list[float]:
    """Custos as deployed today. It can say which *period* is suspect, but every
    decision inside a period looks the same to it — ties are broken at random."""
    return list(s.severity)


def novelty(s: Signals) -> list[float]:
    return list(s.novelty)


def risk_plus_novelty(s: Signals) -> list[float]:
    return [
        0.5 * s.risk_scale(p) + 0.5 * s.novelty_scale(d)
        for p, d in zip(s.risk, s.novelty, strict=True)
    ]


def custos_adaptive(s: Signals) -> list[float]:
    """Proposed. While the population is stable, the model's own risk estimate is
    trustworthy and ranks well; as the population drifts, that estimate is
    extrapolating, and how unfamiliar a request is matters more. The lagged
    severity sets the balance."""
    return [
        w * s.novelty_scale(d) + (1.0 - w) * s.risk_scale(p)
        for p, d, w in zip(s.risk, s.novelty, s.severity, strict=True)
    ]


STRATEGIES: dict[str, Callable[[Signals], list[float]]] = {
    "model_risk": model_risk,
    "low_confidence": low_confidence,
    "population_drift": population_drift,
    "novelty": novelty,
    "risk_plus_novelty": risk_plus_novelty,
    "custos_adaptive": custos_adaptive,
}

PROPOSED = "custos_adaptive"
