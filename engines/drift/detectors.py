"""psi() and ks_test() — pure functions, heavily unit-tested.

Deliberately dependency-free stdlib Python. These are the two statistics the
whole drift signal rests on, so they are kept small enough to read in full and
verify against hand-computed values (see tests/unit/test_detectors.py).

Both answer the same question from different angles:

  PSI  — "has the *shape* of this feature's distribution changed?"  Bucketed,
         sensitive to mass moving between regions, and the number credit-risk
         teams actually report against (bands at 0.10 / 0.25).
  KS   — "what is the largest gap between the two CDFs?"  Bucket-free, so it
         catches shifts that happen to fall inside a single PSI bucket.

Neither returns a p-value. A p-value on production traffic is not useful: with
a large enough sample every distribution differs significantly, so effect size
is what matters operationally.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

# Floor applied to a bucket proportion before taking its logarithm. Without it
# a bucket that is empty in one distribution sends PSI to infinity, which turns
# a single unseen value into a total loss of trust.
_EPSILON = 1e-6


def _clean(values: Sequence[float]) -> list[float]:
    """Drop NaN/inf. A feature pipeline emitting these is a real occurrence."""
    return [float(v) for v in values if v is not None and math.isfinite(float(v))]


def _quantile_edges(values: list[float], buckets: int) -> list[float]:
    """Equal-frequency (quantile) bucket edges from the reference distribution.

    Equal-frequency rather than equal-width: credit features are heavily skewed
    (income, utilisation), and equal-width bucketing puts ~all the mass in one
    bucket, which makes PSI blind to everything happening inside it.

    Returns interior edges only, deduplicated. A feature with heavy point mass
    (e.g. 60% zeros) legitimately yields fewer buckets than requested.

    Edges at or below the minimum are dropped. Ties push quantile boundaries
    onto the same value, and a boundary sitting on the minimum leaves the
    lowest bucket permanently empty — for a constant feature that collapses
    every observation into one bucket and makes PSI identically zero no matter
    how far the live sample has moved. Dropping them costs nothing on a
    well-spread feature and is what lets the caller recognise a degenerate
    reference (no edges left) and handle it explicitly.
    """
    ordered = sorted(values)
    n = len(ordered)
    minimum = ordered[0]

    deduped: list[float] = []
    for i in range(1, buckets):
        edge = ordered[min(int(i * n / buckets), n - 1)]
        if edge > minimum and (not deduped or edge > deduped[-1]):
            deduped.append(edge)
    return deduped


def _bucket_proportions(values: list[float], edges: list[float]) -> list[float]:
    """Fraction of ``values`` falling in each bucket defined by ``edges``."""
    counts = [0] * (len(edges) + 1)
    for value in values:
        # Bisect right: an observation equal to an edge goes in the upper
        # bucket, matching how the edges were drawn from sorted order.
        lo, hi = 0, len(edges)
        while lo < hi:
            mid = (lo + hi) // 2
            if value < edges[mid]:
                hi = mid
            else:
                lo = mid + 1
        counts[lo] += 1

    total = len(values)
    return [c / total for c in counts]


def psi(expected: Sequence[float], actual: Sequence[float], buckets: int = 10) -> float:
    """Population Stability Index between a reference and a live sample.

        PSI = Σ (a_i − e_i) · ln(a_i / e_i)

    Symmetric, zero when the distributions match, and unbounded above. Industry
    reading: < 0.10 stable · 0.10–0.25 moderate shift · > 0.25 significant.

    Raises:
        ValueError: if either sample is empty after removing non-finite values.
            An empty sample is *absence of evidence*, and silently returning 0.0
            would report it as "no drift" — the exact failure ADR 0004 exists to
            prevent. Callers turn this into a degraded signal instead.
    """
    exp, act = _clean(expected), _clean(actual)
    if not exp or not act:
        raise ValueError("psi() requires non-empty expected and actual samples")
    if buckets < 2:
        raise ValueError("psi() requires at least 2 buckets")

    edges = _quantile_edges(exp, buckets)
    if not edges:
        # Reference is a single constant value: drift is binary — either the
        # live sample is that same constant, or the distribution has changed.
        constant = exp[0]
        matching = sum(1 for v in act if v == constant) / len(act)
        return 0.0 if matching == 1.0 else _psi_terms([1.0, 0.0], [matching, 1 - matching])

    return _psi_terms(_bucket_proportions(exp, edges), _bucket_proportions(act, edges))


def _psi_terms(expected_props: list[float], actual_props: list[float]) -> float:
    total = 0.0
    for e, a in zip(expected_props, actual_props, strict=True):
        e, a = max(e, _EPSILON), max(a, _EPSILON)
        total += (a - e) * math.log(a / e)
    return total


def ks_test(expected: Sequence[float], actual: Sequence[float]) -> float:
    """Two-sample Kolmogorov–Smirnov statistic: max |CDF_expected − CDF_actual|.

    Bounded in [0, 1]. 0.0 means the empirical distributions are identical;
    1.0 means their supports are disjoint.

    Returns the statistic only, not a p-value — see the module docstring.

    Raises:
        ValueError: if either sample is empty after cleaning (same reasoning
            as :func:`psi`).
    """
    exp, act = sorted(_clean(expected)), sorted(_clean(actual))
    if not exp or not act:
        raise ValueError("ks_test() requires non-empty expected and actual samples")

    n_exp, n_act = len(exp), len(act)
    i = j = 0
    max_gap = 0.0

    # Single merge pass over both sorted samples. The supremum of the CDF gap
    # can only occur at an observed value, so stepping through every distinct
    # value in order is sufficient — and O(n log n) overall, from the sorts.
    while i < n_exp and j < n_act:
        value = min(exp[i], act[j])
        while i < n_exp and exp[i] == value:
            i += 1
        while j < n_act and act[j] == value:
            j += 1
        max_gap = max(max_gap, abs(i / n_exp - j / n_act))

    # One sample exhausted: the remaining gap only shrinks toward 0, but the
    # boundary point still counts.
    max_gap = max(max_gap, abs(i / n_exp - j / n_act))
    return max_gap
