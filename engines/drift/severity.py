"""Per-feature PSI/KS results -> one severity in [0, 1].

Monotonicity invariant: worse drift never yields a lower severity. See
tests/unit/test_severity.py.

This module is where a pile of statistics becomes a single number an operator
can act on. Two roll-ups happen here:

  1. per feature:  PSI (+ KS) -> severity
  2. across features: many severities -> one model severity
"""

from __future__ import annotations

from shared.config import defaults

# Weight on the worst-drifted feature when rolling up across features.
# Pure max lets one noisy feature dominate the model's severity; pure mean
# lets fifty stable features bury one catastrophically broken feature — which
# is precisely the "one feature's pipeline died" case the drift signal exists
# to catch. Blending keeps both failure modes visible.
#
# Both max() and mean() are monotone non-decreasing in every input, so any
# convex combination of them is too. That is what makes the monotonicity
# invariant hold by construction rather than by testing.
MAX_WEIGHT = 0.6


def psi_to_severity(psi_value: float) -> float:
    """Map a PSI value onto [0, 1] through the industry-standard bands.

    Piecewise-linear with knots at the two thresholds credit-risk teams already
    reason about, so a severity of 0.66 means exactly "PSI just crossed 0.25 —
    significant shift" rather than an arbitrary model-specific number.

        PSI 0.00 -> 0.00     PSI 0.10 -> 0.33 (stable ceiling)
        PSI 0.25 -> 0.66     PSI 0.50 -> 1.00 (saturation)
    """
    psi_value = max(0.0, psi_value)
    stable, moderate, saturation = (
        defaults.PSI_STABLE,
        defaults.PSI_MODERATE,
        defaults.PSI_SATURATION,
    )

    if psi_value <= stable:
        return (psi_value / stable) * (1 / 3)
    if psi_value <= moderate:
        return 1 / 3 + ((psi_value - stable) / (moderate - stable)) * (1 / 3)
    if psi_value <= saturation:
        return 2 / 3 + ((psi_value - moderate) / (saturation - moderate)) * (1 / 3)
    return 1.0


def feature_severity(psi_value: float, ks_value: float | None = None) -> float:
    """Severity for one feature.

    PSI sets the level. KS can only raise it, never lower it: the two statistics
    disagreeing means the shift landed inside a PSI bucket, which is a reason to
    be *more* suspicious, not less. Letting a low KS pull PSI down would create
    a blind spot exactly where bucketing is weakest.
    """
    severity = psi_to_severity(psi_value)
    if ks_value is not None:
        severity = max(severity, min(1.0, max(0.0, ks_value)))
    return min(1.0, severity)


def compute_severity(feature_results: dict[str, float]) -> float:
    """Roll per-feature severities into one model-level severity in [0, 1].

    Args:
        feature_results: ``{feature_name: severity}``, each already in [0, 1].

    Returns:
        0.0 for an empty input — no features means no evidence of drift. The
        caller distinguishes "no drift" from "no data" by never calling this
        with an empty dict; a model with no computed features is reported as
        degraded instead (ADR 0004).
    """
    if not feature_results:
        return 0.0

    severities = [min(1.0, max(0.0, s)) for s in feature_results.values()]
    worst = max(severities)
    mean = sum(severities) / len(severities)
    return min(1.0, MAX_WEIGHT * worst + (1 - MAX_WEIGHT) * mean)


def severity_band(severity: float) -> str:
    """Human label for dashboards and audit reasons."""
    if severity < 1 / 3:
        return "stable"
    if severity < 2 / 3:
        return "moderate"
    return "significant"


def top_contributors(per_feature: dict[str, dict], limit: int = 3) -> list[tuple[str, float]]:
    """The features driving the severity, worst first.

    This is the actionable half of the drift signal: "severity 0.81" tells an
    operator something is wrong, ``[("utilisation", 0.94)]`` tells them where
    to look. Matches how the practitioners interviewed for this project
    actually triage — find the feature, then decide whether it is a genuine
    population shift or a broken pipeline (docs/conversations/01).
    """
    scored = [(name, float(stats.get("severity", 0.0))) for name, stats in per_feature.items()]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:limit]
