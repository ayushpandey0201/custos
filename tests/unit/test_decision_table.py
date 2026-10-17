"""Every row of the decision matrix (§8.6) as a test case.

The cascade in ``services/gateway/decision.py`` *is* the specification, so this
file walks it row by row and then pins the precedence between rows — precedence
is the part that is easy to break silently during a refactor.
"""

from __future__ import annotations

import pytest

from services.gateway.aggregate import AggregateResult
from services.gateway.decision import decide, decide_with_reasons, evaluate_decision
from shared.schemas.decision import Decision
from shared.schemas.signals import VetoInfo

THRESHOLDS = {"block": 0.3, "review": 0.6}


class TestDecisionMatrix:
    @pytest.mark.parametrize(
        "trust,vetoed,model_known,all_degraded,expected",
        [
            # Row 1 — any veto blocks, at any score.
            (1.00, True, True, False, Decision.BLOCK),
            (0.00, True, True, False, Decision.BLOCK),
            (0.95, True, False, True, Decision.BLOCK),
            # Row 2 — below the block threshold.
            (0.00, False, True, False, Decision.BLOCK),
            (0.29, False, True, False, Decision.BLOCK),
            # Row 3 — unregistered model (ADR 0005).
            (1.00, False, False, False, Decision.REVIEW),
            (0.75, False, False, False, Decision.REVIEW),
            # Row 4 — no confident signal from any engine.
            (1.00, False, True, True, Decision.REVIEW),
            # Row 5 (drift floor) is covered in TestDriftFloor.
            # Row 6 — ambiguous score.
            (0.30, False, True, False, Decision.REVIEW),
            (0.59, False, True, False, Decision.REVIEW),
            # Row 7 — allow.
            (0.60, False, True, False, Decision.ALLOW),
            (1.00, False, True, False, Decision.ALLOW),
        ],
    )
    def test_matrix_row(self, trust, vetoed, model_known, all_degraded, expected):
        assert decide(trust, THRESHOLDS, vetoed, model_known, all_degraded) is expected


class TestBoundaries:
    def test_block_threshold_is_exclusive_below(self):
        assert decide(0.2999, THRESHOLDS) is Decision.BLOCK
        assert decide(0.3000, THRESHOLDS) is Decision.REVIEW

    def test_review_threshold_is_inclusive_at_allow(self):
        assert decide(0.5999, THRESHOLDS) is Decision.REVIEW
        assert decide(0.6000, THRESHOLDS) is Decision.ALLOW

    def test_thresholds_are_configurable(self):
        strict = {"block": 0.8, "review": 0.95}
        assert decide(0.9, strict) is Decision.REVIEW
        assert decide(0.7, strict) is Decision.BLOCK
        assert decide(0.99, strict) is Decision.ALLOW

    def test_missing_thresholds_fall_back_to_defaults(self):
        assert decide(0.5, {}) is Decision.REVIEW


class TestPrecedence:
    def test_veto_beats_everything(self):
        assert decide(1.0, THRESHOLDS, vetoed=True, model_known=True) is Decision.BLOCK

    def test_block_score_beats_unknown_model(self):
        """An unregistered model with damning signals is blocked, not flagged."""
        assert decide(0.1, THRESHOLDS, model_known=False) is Decision.BLOCK

    def test_unknown_model_beats_all_degraded(self):
        outcome = decide_with_reasons(0.9, THRESHOLDS, model_known=False, all_degraded=True)
        assert outcome.decision is Decision.REVIEW
        assert "not registered" in outcome.reasons[0]

    def test_all_degraded_beats_a_passing_score(self):
        outcome = decide_with_reasons(1.0, THRESHOLDS, all_degraded=True)
        assert outcome.decision is Decision.REVIEW
        assert "confident signal" in outcome.reasons[0]


class TestQuarantine:
    """Rule 5: an input a person has quarantined holds every decision for review."""

    HELD = {"bureau_score": "stuck at 720 in 100% of recent requests (incident #1)"}

    def test_a_quarantine_holds_an_otherwise_perfect_decision(self):
        outcome = decide_with_reasons(1.0, THRESHOLDS, quarantined=self.HELD)
        assert outcome.decision is Decision.REVIEW
        assert "bureau_score" in outcome.reasons[0]
        assert "incident #1" in outcome.reasons[0]

    def test_a_quarantine_never_softens_a_block(self):
        assert decide(0.1, THRESHOLDS, quarantined=self.HELD) is Decision.BLOCK
        assert decide(1.0, THRESHOLDS, vetoed=True, quarantined=self.HELD) is Decision.BLOCK

    def test_an_unknown_model_is_reported_as_unknown_first(self):
        outcome = decide_with_reasons(1.0, THRESHOLDS, model_known=False, quarantined=self.HELD)
        assert "not registered" in outcome.reasons[0]

    def test_quarantine_is_named_ahead_of_drift(self):
        """The precise cause beats the symptom: the dead feed is *why* it drifted."""
        outcome = decide_with_reasons(
            0.9, THRESHOLDS, drift_significant=True, quarantined=self.HELD
        )
        assert "quarantined" in outcome.reasons[0]

    def test_every_held_input_is_named(self):
        held = {"a": "missing", "b": "stuck"}
        reasons = decide_with_reasons(1.0, THRESHOLDS, quarantined=held).reasons
        assert len(reasons) == 2

    def test_no_quarantine_changes_nothing(self):
        assert decide(0.95, THRESHOLDS, quarantined={}) is Decision.ALLOW
        assert decide(0.95, THRESHOLDS, quarantined=None) is Decision.ALLOW


class TestDriftFloor:
    """Rule 6: a significantly drifted model is never auto-approved.

    This used to hold only because the stub risk engine was always excluded,
    which happened to leave drift enough weight. These tests pin it as a rule.
    """

    def test_significant_drift_stops_an_otherwise_passing_score(self):
        outcome = decide_with_reasons(0.95, THRESHOLDS, drift_significant=True)
        assert outcome.decision is Decision.REVIEW
        assert "significant" in outcome.reasons[0]

    def test_drift_floor_never_softens_a_block(self):
        assert decide(0.1, THRESHOLDS, drift_significant=True) is Decision.BLOCK
        assert decide(1.0, THRESHOLDS, vetoed=True, drift_significant=True) is Decision.BLOCK

    def test_without_significant_drift_the_score_decides(self):
        assert decide(0.95, THRESHOLDS, drift_significant=False) is Decision.ALLOW

    def test_the_weights_alone_can_no_longer_guarantee_this(self):
        """Why the rule exists: with all three engines live, a drifted model can
        out-score the review threshold. severity 0.75 -> drift score 0.25."""
        weights = {"policy": 0.3, "drift": 0.5, "risk": 0.2}
        fused = weights["policy"] * 1.0 + weights["drift"] * 0.25 + weights["risk"] * 1.0
        assert fused >= THRESHOLDS["review"]  # the average alone would ALLOW
        assert decide(fused, THRESHOLDS, drift_significant=True) is Decision.REVIEW


class TestReasons:
    def test_every_decision_carries_a_reason(self):
        cases = [
            (1.0, True, True, False),
            (0.1, False, True, False),
            (0.9, False, False, False),
            (0.9, False, True, True),
            (0.4, False, True, False),
            (0.9, False, True, False),
        ]
        for trust, vetoed, known, degraded in cases:
            outcome = decide_with_reasons(trust, THRESHOLDS, vetoed, known, degraded)
            assert outcome.reasons and outcome.reasons[0].strip()

    def test_reason_names_the_threshold_that_was_crossed(self):
        assert "0.30" in decide_with_reasons(0.1, THRESHOLDS).reasons[0]
        assert "0.60" in decide_with_reasons(0.4, THRESHOLDS).reasons[0]


class TestEvaluateDecision:
    def test_veto_detail_is_appended_to_reasons(self):
        result = AggregateResult(
            score=0.0,
            vetoes=[VetoInfo(engine="policy", reason="amount over limit", rule_id="r1")],
        )
        outcome = evaluate_decision(result, THRESHOLDS)
        assert outcome.decision is Decision.BLOCK
        assert any("amount over limit" in r for r in outcome.reasons)

    def test_degraded_engines_are_named_in_reasons(self):
        result = AggregateResult(score=0.9, degraded_engines=["risk"])
        outcome = evaluate_decision(result, THRESHOLDS)
        assert outcome.decision is Decision.ALLOW
        assert any("risk" in r for r in outcome.reasons)

    def test_all_degraded_does_not_also_list_excluded_engines(self):
        """When nothing ran, 'excluded from fusion' would be noise."""
        result = AggregateResult(
            score=1.0, degraded_engines=["policy", "drift", "risk"], all_degraded=True
        )
        outcome = evaluate_decision(result, THRESHOLDS)
        assert outcome.decision is Decision.REVIEW
        assert not any("excluded from fusion" in r for r in outcome.reasons)

    def test_unknown_model_propagates_through(self):
        result = AggregateResult(score=0.95)
        assert evaluate_decision(result, THRESHOLDS, model_known=False).decision is Decision.REVIEW
