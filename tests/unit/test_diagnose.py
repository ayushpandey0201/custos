"""Diagnosis: a broken feed and a real population shift must never be confused.

The cost of the two mistakes is not symmetric. Calling a shift a broken feed
holds decisions that were fine. Calling a broken feed a shift is worse: the
natural response to a shift is to re-baseline, and re-baselining on a broken
feed teaches the drift alarm that broken data is normal.
"""

from __future__ import annotations

import random

import pytest

from services.healing.diagnose import MIN_WINDOW, diagnose

POPULATION = {
    "income": (60000.0, 15000.0),
    "utilisation": (0.35, 0.12),
    "bureau_score": (720.0, 60.0),
}


def applicants(rng: random.Random, n: int, shift: dict | None = None) -> list[dict]:
    shift = shift or {}
    return [
        {
            name: rng.gauss(mu, sigma) + shift.get(name, 0.0)
            for name, (mu, sigma) in POPULATION.items()
        }
        for _ in range(n)
    ]


def columns(rows: list[dict]) -> dict[str, list[float]]:
    return {name: [r[name] for r in rows] for name in rows[0]}


@pytest.fixture
def baseline(rng):
    return columns(applicants(rng, 600))


def status_of(diagnosis, name: str) -> str:
    return next(i.status for i in diagnosis.inputs if i.name == name)


class TestHealthy:
    def test_traffic_from_the_baseline_population_is_healthy(self, rng, baseline):
        d = diagnose(baseline, applicants(rng, 200))
        assert d.kind == "healthy"
        assert all(i.status == "ok" for i in d.inputs)

    def test_too_little_traffic_is_reported_not_guessed(self, rng, baseline):
        d = diagnose(baseline, applicants(rng, MIN_WINDOW - 1))
        assert d.kind == "insufficient_data"


class TestPipelineBreak:
    def test_a_feature_pinned_to_one_value_is_a_broken_feed(self, rng, baseline):
        rows = applicants(rng, 200)
        for row in rows:
            row["bureau_score"] = 720.0
        d = diagnose(baseline, rows)
        assert d.kind == "pipeline_break"
        assert status_of(d, "bureau_score") == "stuck"
        assert "720" in next(i.detail for i in d.broken)

    def test_pinned_at_the_mean_is_still_caught(self, rng, baseline):
        """A default-fill at the population mean barely moves the average —
        a monitor watching means would miss it. The spread collapses, though."""
        rows = applicants(rng, 200)
        mean = sum(baseline["bureau_score"]) / len(baseline["bureau_score"])
        for row in rows:
            row["bureau_score"] = mean
        assert diagnose(baseline, rows).kind == "pipeline_break"

    def test_a_feature_that_stops_arriving_is_a_broken_feed(self, rng, baseline):
        rows = applicants(rng, 200)
        for row in rows:
            del row["income"]
        d = diagnose(baseline, rows)
        assert d.kind == "pipeline_break"
        assert status_of(d, "income") == "missing"

    @pytest.mark.parametrize("bad", [None, float("nan"), "N/A"])
    def test_nulls_nans_and_strings_count_as_missing(self, rng, baseline, bad):
        rows = applicants(rng, 200)
        for row in rows:
            row["utilisation"] = bad
        assert status_of(diagnose(baseline, rows), "utilisation") == "missing"

    def test_a_partly_broken_feed_below_threshold_is_not_flagged(self, rng, baseline):
        rows = applicants(rng, 200)
        for row in rows[:60]:  # 30% missing: degraded, not dead
            del row["income"]
        assert status_of(diagnose(baseline, rows), "income") != "missing"

    def test_broken_feed_wins_over_a_simultaneous_shift(self, rng, baseline):
        """Nothing should be re-learned while part of the input is garbage."""
        rows = applicants(rng, 200, shift={"income": -40000})
        for row in rows:
            row["bureau_score"] = 0.0
        d = diagnose(baseline, rows)
        assert d.kind == "pipeline_break"
        assert status_of(d, "income") == "shifted"  # still reported


class TestPointMass:
    """Inputs that legitimately have one very common value (e.g. 60% zeros)."""

    @pytest.fixture
    def sparse_baseline(self, rng):
        return {
            "balance": [0.0 if rng.random() < 0.6 else rng.uniform(1, 1000) for _ in range(600)]
        }

    def test_the_usual_point_mass_is_not_a_fault(self, rng, sparse_baseline):
        rows = [
            {"balance": 0.0 if rng.random() < 0.6 else rng.uniform(1, 1000)} for _ in range(200)
        ]
        assert diagnose(sparse_baseline, rows).kind == "healthy"

    def test_collapsing_onto_the_point_mass_is_a_fault(self, sparse_baseline):
        rows = [{"balance": 0.0} for _ in range(200)]
        assert diagnose(sparse_baseline, rows).kind == "pipeline_break"


class TestPopulationShift:
    def test_a_real_shift_is_a_shift_not_a_break(self, rng, baseline):
        d = diagnose(baseline, applicants(rng, 200, shift={"income": -30000, "utilisation": 0.4}))
        assert d.kind == "population_shift"
        assert not d.broken

    def test_only_the_inputs_that_moved_are_blamed(self, rng, baseline):
        d = diagnose(baseline, applicants(rng, 200, shift={"income": -30000, "utilisation": 0.4}))
        assert {i.name for i in d.shifted} == {"income", "utilisation"}
        assert status_of(d, "bureau_score") == "ok"

    def test_a_small_shift_does_not_open_an_incident(self, rng, baseline):
        assert diagnose(baseline, applicants(rng, 200, shift={"income": 1000})).kind == "healthy"
