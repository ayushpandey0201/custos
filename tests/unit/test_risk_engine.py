"""RiskEngine: unusual amounts and request bursts, and refusing to guess without data."""

from __future__ import annotations

import pytest

from engines.risk import engine as risk
from engines.risk.engine import RiskEngine
from shared.schemas.evaluation import EvaluationContext


def ctx(tenant: str = "acme", model: str = "m", **context) -> EvaluationContext:
    return EvaluationContext(tenant_id=tenant, model_id=model, context=context)


async def score(**context):
    return await RiskEngine().evaluate(ctx(**context))


async def warm(amount: float = 100_000.0, n: int = risk.MIN_HISTORY, **context) -> None:
    for i in range(n):
        # A little spread, like real traffic.
        await score(amount=amount * (0.9 + 0.2 * (i % 11) / 10), **context)


pytestmark = pytest.mark.asyncio


class TestRefusingToGuess:
    async def test_no_context_at_all_is_degraded(self):
        result = await score()
        assert result.degraded
        assert result.detail["reason"] == "insufficient_context"

    async def test_amount_history_too_short_is_degraded_not_safe(self):
        """Without a history there is no "normal" to compare against."""
        result = await score(amount=5_000_000)
        assert result.degraded
        assert "warming up" in result.detail["abstained"]["amount"]

    async def test_non_numeric_amount_does_not_vote(self):
        await warm()
        result = await score(amount="lots")
        assert result.degraded


class TestAmount:
    async def test_typical_amount_carries_no_risk(self):
        await warm()
        result = await score(amount=100_000)
        assert not result.degraded
        assert result.score == pytest.approx(1.0)
        assert result.detail["driven_by"] is None

    async def test_extreme_amount_is_maximum_risk(self):
        await warm()
        result = await score(amount=2_000_000)
        assert result.score == pytest.approx(0.0)
        assert result.detail["driven_by"] == "amount"
        assert result.detail["components"]["amount"]["robust_z"] > risk.Z_MAX

    async def test_risk_rises_monotonically_with_amount(self):
        await warm()
        scores = []
        for amount in (100_000, 150_000, 200_000, 300_000, 600_000, 1_000_000):
            scores.append((await score(amount=amount)).score)
        assert scores == sorted(scores, reverse=True), scores

    async def test_small_amounts_are_not_risky(self):
        """Only the upper tail matters: a tiny loan is not dangerous."""
        await warm()
        assert (await score(amount=10)).score == pytest.approx(1.0)

    async def test_uniform_history_does_not_make_every_difference_extreme(self):
        """MAD = 0 would make *any* change look infinitely anomalous."""
        for _ in range(risk.MIN_HISTORY):
            await score(amount=200_000)
        assert (await score(amount=210_000)).score == pytest.approx(1.0)
        assert (await score(amount=900_000)).score == pytest.approx(0.0)

    async def test_outliers_cannot_drag_the_baseline(self):
        """A robust median ignores a handful of extreme values in the history."""
        await warm()
        for _ in range(5):
            await score(amount=50_000_000)
        assert (await score(amount=100_000)).score == pytest.approx(1.0)


class TestVelocity:
    async def test_a_burst_from_one_customer_is_risky(self):
        results = [await score(customer_id="c-1") for _ in range(risk.RATE_MAX)]
        assert results[0].score == pytest.approx(1.0)
        assert results[-1].score == pytest.approx(0.0)
        assert results[-1].detail["driven_by"] == "velocity"

    async def test_different_customers_do_not_share_a_budget(self):
        for i in range(risk.RATE_MAX):
            assert (await score(customer_id=f"c-{i}")).score == pytest.approx(1.0)

    async def test_alternative_subject_keys_are_recognised(self):
        for key in risk.SUBJECT_KEYS:
            assert not (await score(**{key: "x"})).degraded


class TestCombination:
    async def test_worst_component_wins(self):
        """Averaging would let a quiet velocity hide an extreme amount."""
        await warm(customer_id="steady")
        result = await score(amount=5_000_000, customer_id="first-time")
        assert result.score == pytest.approx(0.0)
        assert result.detail["driven_by"] == "amount"


class TestTenantIsolation:
    async def test_one_tenants_history_never_informs_anothers(self):
        for _ in range(risk.MIN_HISTORY):
            await RiskEngine().evaluate(ctx(tenant="small", amount=1_000))
        # "big" has never been seen: its amount component must abstain, not
        # judge against "small"'s idea of normal.
        result = await RiskEngine().evaluate(ctx(tenant="big", amount=1_000_000))
        assert result.degraded

    async def test_velocity_is_per_tenant(self):
        for _ in range(risk.RATE_MAX):
            await RiskEngine().evaluate(ctx(tenant="a", customer_id="same"))
        result = await RiskEngine().evaluate(ctx(tenant="b", customer_id="same"))
        assert result.score == pytest.approx(1.0)
