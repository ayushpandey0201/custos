"""psi() and ks_test() against known distributions (golden tests).

These two functions are the foundation of the drift signal. If they are wrong,
every severity, every trust score and every BLOCK downstream is wrong with
them — so they are tested against hand-computable cases rather than only
against each other.
"""

from __future__ import annotations

import math

import pytest

from engines.drift.detectors import ks_test, psi
from tests.conftest import normal_sample


class TestPsi:
    def test_identical_distributions_score_zero(self, rng):
        sample = normal_sample(rng, 0, 1, 1000)
        assert psi(sample, sample) == pytest.approx(0.0, abs=1e-9)

    def test_golden_value_two_buckets(self):
        """Hand-computed against the PSI definition.

        Reference splits 50/50 at the median; live is 80/20.
            PSI = (0.8-0.5)·ln(0.8/0.5) + (0.2-0.5)·ln(0.2/0.5)
                = 0.3·0.470004 + (-0.3)·(-0.916291) = 0.415888
        """
        expected = [0.0] * 50 + [1.0] * 50
        actual = [0.0] * 80 + [1.0] * 20
        hand_computed = 0.3 * math.log(0.8 / 0.5) + (-0.3) * math.log(0.2 / 0.5)
        assert psi(expected, actual, buckets=2) == pytest.approx(hand_computed, abs=1e-6)

    def test_is_symmetric(self, rng):
        a = normal_sample(rng, 0, 1, 400)
        b = normal_sample(rng, 0.5, 1, 400)
        # PSI's (a-e)·ln(a/e) form is symmetric under swapping the two samples
        # only when the bucket edges are shared; they are not, so allow a loose
        # tolerance. The property that matters is that neither direction is
        # dramatically different.
        assert psi(a, b, buckets=5) == pytest.approx(psi(b, a, buckets=5), rel=0.35)

    def test_larger_shift_gives_larger_psi(self, rng):
        reference = normal_sample(rng, 0, 1, 1000)
        small = normal_sample(rng, 0.25, 1, 1000)
        large = normal_sample(rng, 2.0, 1, 1000)
        assert psi(reference, small) < psi(reference, large)

    def test_shift_crosses_industry_bands(self, rng):
        """A 1-sigma mean shift must read as 'significant' (PSI > 0.25)."""
        reference = normal_sample(rng, 0, 1, 2000)
        shifted = normal_sample(rng, 1.0, 1, 2000)
        assert psi(reference, shifted) > 0.25

    def test_stable_resample_stays_in_stable_band(self, rng):
        """Two draws from the same distribution must read as stable (< 0.10)."""
        assert psi(normal_sample(rng, 0, 1, 2000), normal_sample(rng, 0, 1, 2000)) < 0.10

    def test_empty_sample_raises_rather_than_scoring_zero(self):
        # Absence of evidence must never be reported as evidence of stability;
        # the caller turns this into a degraded signal (ADR 0004).
        with pytest.raises(ValueError):
            psi([], [1.0, 2.0])
        with pytest.raises(ValueError):
            psi([1.0, 2.0], [])

    def test_non_finite_values_are_ignored(self):
        clean = [1.0, 2.0, 3.0, 4.0]
        dirty = [1.0, float("nan"), 2.0, float("inf"), 3.0, 4.0]
        assert psi(clean, dirty, buckets=2) == pytest.approx(psi(clean, clean, buckets=2), abs=1e-9)

    def test_constant_reference_matched_exactly_is_zero(self):
        assert psi([5.0] * 100, [5.0] * 100) == 0.0

    def test_constant_reference_that_moves_is_flagged(self):
        """A feature pinned to one value that starts varying is a pipeline break."""
        assert psi([5.0] * 100, [5.0] * 50 + [9.0] * 50) > 0.25

    def test_heavy_point_mass_does_not_explode(self):
        """60% zeros collapses bucket edges; PSI must stay finite."""
        expected = [0.0] * 60 + [float(i) for i in range(1, 41)]
        actual = [0.0] * 55 + [float(i) for i in range(1, 46)]
        assert math.isfinite(psi(expected, actual))

    def test_disjoint_supports_stay_finite(self):
        """Epsilon smoothing: an empty bucket must not send PSI to infinity."""
        assert math.isfinite(psi([1.0] * 50 + [2.0] * 50, [100.0] * 100, buckets=5))

    def test_rejects_degenerate_bucket_count(self):
        with pytest.raises(ValueError):
            psi([1.0, 2.0], [1.0, 2.0], buckets=1)


class TestKsTest:
    def test_identical_samples_score_zero(self):
        sample = [float(i) for i in range(100)]
        assert ks_test(sample, sample) == pytest.approx(0.0)

    def test_disjoint_supports_score_one(self):
        assert ks_test([0.0] * 50, [1.0] * 50) == pytest.approx(1.0)

    def test_golden_value_half_shift(self):
        """Half of the live sample moved above the reference's entire range.

        Reference is 0..99; live is 0..49 plus fifty values above 1000. At the
        top of the reference range CDF_expected = 1.0 while CDF_actual = 0.5,
        so the maximum gap is exactly 0.5.
        """
        expected = [float(i) for i in range(100)]
        actual = [float(i) for i in range(50)] + [1000.0 + i for i in range(50)]
        assert ks_test(expected, actual) == pytest.approx(0.5, abs=1e-9)

    def test_is_bounded_in_unit_interval(self, rng):
        for mu in (0, 0.5, 3.0, 10.0):
            value = ks_test(normal_sample(rng, 0, 1, 300), normal_sample(rng, mu, 1, 300))
            assert 0.0 <= value <= 1.0

    def test_is_symmetric(self, rng):
        a = normal_sample(rng, 0, 1, 300)
        b = normal_sample(rng, 1, 1, 300)
        assert ks_test(a, b) == pytest.approx(ks_test(b, a))

    def test_larger_shift_gives_larger_statistic(self, rng):
        reference = normal_sample(rng, 0, 1, 800)
        small = ks_test(reference, normal_sample(rng, 0.3, 1, 800))
        large = ks_test(reference, normal_sample(rng, 2.0, 1, 800))
        assert small < large

    def test_empty_sample_raises(self):
        with pytest.raises(ValueError):
            ks_test([], [1.0])

    def test_catches_shift_hidden_inside_a_psi_bucket(self):
        """Why both statistics exist.

        Every live value sits inside the reference's single bucket span, so
        coarse bucketing sees little; KS still measures the CDF gap directly.
        """
        expected = [float(i) for i in range(100)]
        actual = [50.0] * 100
        assert ks_test(expected, actual) > 0.45
