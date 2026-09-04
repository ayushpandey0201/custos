"""Roll-up monotonicity: worse drift never yields a lower severity.

That invariant is the whole contract of this module. If it can be violated,
then a model getting worse can produce a *higher* trust score, and every
threshold downstream becomes meaningless.
"""

from __future__ import annotations

import random

import pytest

from engines.drift.severity import (
    MAX_WEIGHT,
    compute_severity,
    feature_severity,
    psi_to_severity,
    severity_band,
    top_contributors,
)
from shared.config import defaults


class TestPsiToSeverity:
    def test_zero_psi_is_zero_severity(self):
        assert psi_to_severity(0.0) == 0.0

    def test_band_knots_land_where_documented(self):
        assert psi_to_severity(defaults.PSI_STABLE) == pytest.approx(1 / 3)
        assert psi_to_severity(defaults.PSI_MODERATE) == pytest.approx(2 / 3)
        assert psi_to_severity(defaults.PSI_SATURATION) == pytest.approx(1.0)

    def test_saturates_at_one(self):
        assert psi_to_severity(5.0) == 1.0
        assert psi_to_severity(1e9) == 1.0

    def test_is_monotone_non_decreasing(self):
        values = [i / 200 for i in range(0, 200)]
        severities = [psi_to_severity(v) for v in values]
        assert all(b >= a for a, b in zip(severities, severities[1:], strict=False))

    def test_negative_psi_clamps_to_zero(self):
        # PSI cannot be negative, but a caller passing one must not produce a
        # negative severity that would inflate trust above 1.0 downstream.
        assert psi_to_severity(-1.0) == 0.0

    def test_bands_are_labelled_consistently(self):
        assert severity_band(psi_to_severity(0.05)) == "stable"
        assert severity_band(psi_to_severity(0.18)) == "moderate"
        assert severity_band(psi_to_severity(0.40)) == "significant"


class TestFeatureSeverity:
    def test_ks_can_only_raise_severity(self):
        psi_only = feature_severity(0.05)
        assert feature_severity(0.05, ks_value=0.9) > psi_only
        # A low KS must not pull a high PSI down — disagreement means the shift
        # hid inside a bucket, which is a reason for more suspicion, not less.
        assert feature_severity(0.40, ks_value=0.01) == feature_severity(0.40)

    def test_is_bounded(self):
        assert feature_severity(100.0, ks_value=1.0) == 1.0
        assert 0.0 <= feature_severity(0.0, ks_value=0.0) <= 1.0

    def test_out_of_range_ks_is_clamped(self):
        assert feature_severity(0.0, ks_value=5.0) == 1.0
        assert feature_severity(0.0, ks_value=-5.0) == 0.0


class TestComputeSeverity:
    def test_empty_input_is_zero(self):
        assert compute_severity({}) == 0.0

    def test_single_feature_passes_through(self):
        assert compute_severity({"a": 0.42}) == pytest.approx(0.42)

    def test_blends_worst_and_mean_as_documented(self):
        result = compute_severity({"a": 1.0, "b": 0.0})
        expected = MAX_WEIGHT * 1.0 + (1 - MAX_WEIGHT) * 0.5
        assert result == pytest.approx(expected)

    def test_monotone_in_every_feature(self):
        """The core invariant, checked exhaustively over random perturbations.

        Raising any single feature's severity must never lower the roll-up.
        """
        rng = random.Random(20260904)
        for _ in range(500):
            base = {f"f{i}": rng.random() for i in range(rng.randint(1, 8))}
            before = compute_severity(base)

            key = rng.choice(list(base))
            worse = dict(base)
            worse[key] = min(1.0, base[key] + rng.random() * (1 - base[key]))

            assert compute_severity(worse) >= before - 1e-12

    def test_adding_a_worse_feature_never_lowers_severity(self):
        base = {"a": 0.2, "b": 0.3}
        assert compute_severity({**base, "c": 0.9}) >= compute_severity(base)

    def test_one_broken_feature_is_not_buried_by_many_stable_ones(self):
        """The failure mode a pure mean would hide.

        Fifty healthy features plus one dead pipeline must still register well
        above the 'stable' band.
        """
        features = {f"f{i}": 0.0 for i in range(50)}
        features["broken"] = 1.0
        assert compute_severity(features) > 1 / 3

    def test_one_noisy_feature_does_not_max_out_the_model(self):
        """The failure mode a pure max would cause."""
        features = {f"f{i}": 0.0 for i in range(10)}
        features["noisy"] = 1.0
        assert compute_severity(features) < 1.0

    def test_result_is_bounded(self):
        assert compute_severity({"a": 5.0, "b": -3.0}) <= 1.0
        assert compute_severity({"a": -3.0}) >= 0.0

    def test_all_stable_stays_stable(self):
        assert compute_severity({f"f{i}": 0.05 for i in range(6)}) < 1 / 3


class TestTopContributors:
    def test_returns_worst_first(self):
        per_feature = {
            "income": {"severity": 0.2},
            "utilisation": {"severity": 0.9},
            "age": {"severity": 0.5},
        }
        assert [name for name, _ in top_contributors(per_feature)] == [
            "utilisation",
            "age",
            "income",
        ]

    def test_respects_limit(self):
        per_feature = {f"f{i}": {"severity": i / 10} for i in range(10)}
        assert len(top_contributors(per_feature, limit=3)) == 3

    def test_handles_missing_severity_key(self):
        assert top_contributors({"a": {}}) == [("a", 0.0)]

    def test_empty_input(self):
        assert top_contributors({}) == []
