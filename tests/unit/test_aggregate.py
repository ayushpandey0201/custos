"""Weighted mean, veto ceiling, degraded exclusion."""

from __future__ import annotations

import pytest

from services.gateway.aggregate import VETO_CEILING, aggregate
from shared.schemas.signals import SignalResult, VetoInfo

WEIGHTS = {"policy": 0.3, "drift": 0.5, "risk": 0.2}


def signal(engine: str, score: float, degraded: bool = False, veto: VetoInfo | None = None):
    return SignalResult(engine=engine, score=score, degraded=degraded, veto=veto)


class TestWeightedMean:
    def test_all_engines_agreeing(self):
        signals = [signal("policy", 0.8), signal("drift", 0.8), signal("risk", 0.8)]
        assert aggregate(signals, WEIGHTS).score == pytest.approx(0.8)

    def test_weights_are_applied(self):
        signals = [signal("policy", 1.0), signal("drift", 0.0), signal("risk", 1.0)]
        # (0.3·1.0 + 0.5·0.0 + 0.2·1.0) / 1.0
        assert aggregate(signals, WEIGHTS).score == pytest.approx(0.5)

    def test_drift_carries_the_most_weight(self):
        """Design intent, asserted: drift moves the score more than policy."""
        drift_bad = aggregate([signal("policy", 1.0), signal("drift", 0.0)], WEIGHTS).score
        policy_bad = aggregate([signal("policy", 0.0), signal("drift", 1.0)], WEIGHTS).score
        assert drift_bad < policy_bad

    def test_result_is_bounded(self):
        assert 0.0 <= aggregate([signal("drift", 1.0)], WEIGHTS).score <= 1.0
        assert 0.0 <= aggregate([signal("drift", 0.0)], WEIGHTS).score <= 1.0

    def test_contributions_sum_to_one(self):
        result = aggregate([signal("policy", 0.5), signal("drift", 0.5)], WEIGHTS)
        assert sum(result.contributions.values()) == pytest.approx(1.0)


class TestDegradedExclusion:
    def test_degraded_signal_is_excluded_from_the_mean(self):
        """A degraded engine must not contribute a free 1.0 (ADR 0004)."""
        with_degraded = aggregate(
            [signal("policy", 0.4), signal("drift", 1.0, degraded=True)], WEIGHTS
        )
        policy_only = aggregate([signal("policy", 0.4)], WEIGHTS)
        assert with_degraded.score == pytest.approx(policy_only.score)
        assert with_degraded.score == pytest.approx(0.4)

    def test_degraded_engines_are_reported(self):
        result = aggregate([signal("policy", 1.0), signal("drift", 1.0, degraded=True)], WEIGHTS)
        assert result.degraded_engines == ["drift"]
        assert not result.all_degraded

    def test_surviving_weights_are_renormalised(self):
        """Removing an engine reweights the rest rather than dragging toward 0."""
        result = aggregate(
            [signal("policy", 0.6), signal("drift", 0.6), signal("risk", 1.0, degraded=True)],
            WEIGHTS,
        )
        assert result.score == pytest.approx(0.6)
        assert sum(result.contributions.values()) == pytest.approx(1.0)
        assert "risk" not in result.contributions

    def test_all_degraded_is_flagged(self):
        result = aggregate(
            [signal("policy", 1.0, degraded=True), signal("drift", 1.0, degraded=True)], WEIGHTS
        )
        assert result.all_degraded
        assert set(result.degraded_engines) == {"policy", "drift"}
        assert result.contributions == {}

    def test_no_signals_at_all_is_all_degraded(self):
        assert aggregate([], WEIGHTS).all_degraded

    def test_unweighted_engine_does_not_contribute(self):
        """An engine that is running but has no weight is a config mistake.

        It must not silently get a default weight; ``contributions`` makes the
        omission visible instead.
        """
        result = aggregate([signal("policy", 0.2), signal("mystery", 1.0)], {"policy": 1.0})
        assert result.score == pytest.approx(0.2)
        assert "mystery" not in result.contributions

    def test_zero_total_weight_is_all_degraded(self):
        assert aggregate([signal("policy", 0.9)], {"policy": 0.0}).all_degraded


class TestVetoCeiling:
    def test_veto_forces_the_score_to_the_ceiling(self):
        veto = VetoInfo(engine="policy", reason="forbidden action", rule_id="r1")
        result = aggregate([signal("policy", 0.0, veto=veto), signal("drift", 1.0)], WEIGHTS)
        assert result.score == VETO_CEILING
        assert result.vetoed

    def test_no_amount_of_agreement_outvotes_a_veto(self):
        veto = VetoInfo(engine="policy", reason="forbidden", rule_id="r1")
        signals = [
            signal("policy", 1.0, veto=veto),
            signal("drift", 1.0),
            signal("risk", 1.0),
        ]
        assert aggregate(signals, WEIGHTS).score == VETO_CEILING

    def test_veto_survives_when_every_other_engine_is_degraded(self):
        veto = VetoInfo(engine="policy", reason="forbidden", rule_id="r1")
        result = aggregate(
            [signal("policy", 0.0, veto=veto), signal("drift", 1.0, degraded=True)],
            {"drift": 1.0},
        )
        assert result.vetoed
        assert result.score == VETO_CEILING

    def test_vetoes_are_reported(self):
        veto = VetoInfo(engine="policy", reason="amount over limit", rule_id="max-amount")
        result = aggregate([signal("policy", 0.0, veto=veto)], WEIGHTS)
        assert [v.rule_id for v in result.vetoes] == ["max-amount"]

    def test_no_veto_leaves_vetoed_false(self):
        assert not aggregate([signal("drift", 0.1)], WEIGHTS).vetoed
