"""Small, exact statistics: ranks, AUC, Spearman, permutation tests, Wilson CIs."""

from __future__ import annotations

import math
import random
from bisect import bisect_right
from collections.abc import Sequence


def average_ranks(values: Sequence[float]) -> list[float]:
    """1-based ranks; tied values share the average of their positions."""
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def auc(scores: Sequence[float], labels: Sequence[int]) -> float | None:
    """Area under the ROC curve via Mann–Whitney. None when only one class is present."""
    positives = sum(labels)
    negatives = len(labels) - positives
    if not positives or not negatives:
        return None
    ranks = average_ranks(scores)
    rank_sum = sum(r for r, y in zip(ranks, labels, strict=True) if y)
    return (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def _pearson(a: Sequence[float], b: Sequence[float]) -> float | None:
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    if not sa or not sb:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=True)) / (sa * sb)


def spearman(a: Sequence[float], b: Sequence[float]) -> float | None:
    if len(a) != len(b) or len(a) < 3:
        return None
    return _pearson(average_ranks(a), average_ranks(b))


def permutation_p(
    a: Sequence[float], b: Sequence[float], n_perm: int = 10_000, seed: int = 0
) -> float | None:
    """Two-sided p-value for Spearman ρ by shuffling one series.

    Exact enough for the dozen-or-so windows this study has, and it makes no
    distributional assumption a reviewer could object to.
    """
    observed = spearman(a, b)
    if observed is None:
        return None
    rng = random.Random(seed)
    shuffled = list(b)
    extreme = 0
    for _ in range(n_perm):
        rng.shuffle(shuffled)
        rho = spearman(a, shuffled)
        if rho is not None and abs(rho) >= abs(observed) - 1e-12:
            extreme += 1
    return (extreme + 1) / (n_perm + 1)


def wilson(successes: float, trials: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion."""
    if trials <= 0:
        return 0.0, 1.0
    p = successes / trials
    centre = (p + z * z / (2 * trials)) / (1 + z * z / trials)
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials))
    half /= 1 + z * z / trials
    return max(0.0, centre - half), min(1.0, centre + half)


class ECDF:
    """Empirical CDF of a reference sample: turns any score into a percentile.

    Built from *training* data, so a percentile means "higher than this share
    of what the model was trained on" — a causal scale, not one fitted to the
    period being evaluated.
    """

    def __init__(self, reference: Sequence[float]) -> None:
        if not reference:
            raise ValueError("ECDF needs a non-empty reference")
        self._sorted = sorted(reference)

    def __call__(self, value: float) -> float:
        return bisect_right(self._sorted, value) / len(self._sorted)
