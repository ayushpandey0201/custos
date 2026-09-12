"""What breaks when requests arrive at the same time rather than one after another.

Every other test in this suite drives the gateway through ``TestClient``, which
issues one request at a time. That is the right shape for testing *decisions* —
and it means the entire suite could pass on a system that corrupts its audit
chain the moment two callers arrive together.

Two properties are worth pinning here, and they fail in different ways:

* **The hash chain survives concurrent appends.** ``seq`` is allocated by
  reading the current head, so simultaneous appends race for the same number.
  These tests exist because that race used to drop entries outright: a decision
  would be returned to the caller with no evidence behind it, under exactly the
  load where an auditor would care most. Worse, the surviving chain still
  verified, so nothing reported the loss.

* **Concurrent requests do not blow the latency budget.** This asserts against
  a deliberately loose multiple of the 50 ms target, because wall-clock
  assertions on shared CI hardware are how a suite becomes flaky. It is a
  regression guard against an order-of-magnitude change — someone putting an
  unbounded query or a network call on the hot path — not a measurement.
  The measurement lives in ``benchmarks/load_test.py``, which is the only
  thing that should ever be quoted as this system's p99.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from services.gateway.audit import verify_chain
from services.gateway.main import create_app
from tests.conftest import TEST_API_KEY

# Loose on purpose — see the module docstring.
LATENCY_CEILING_MS = 500.0

# These two started as expected failures. `append_to_chain` used to retry five
# times with no backoff, so concurrent appenders stayed in lockstep, collided
# repeatedly, and 1-3% of entries were dropped outright at 10-32 writers —
# while `verify_chain` still reported the result valid, because hash chaining
# detects a *modified* entry but not a *missing* one.
#
# Fixed by jittered backoff plus a Postgres advisory lock (see
# services/gateway/audit.py). Kept at 24 writers because that is roughly four
# times the level where drops used to begin.


def auth() -> dict:
    return {"X-API-Key": TEST_API_KEY}


class TestConcurrentAuditAppends:
    """The hash chain under simultaneous writers."""

    def _append(self, index: int) -> str:
        from services.gateway import audit
        from shared.schemas.decision import Decision, DecisionRecord

        record = audit.build_record(
            DecisionRecord(
                decision=Decision.ALLOW,
                trust_score=1.0,
                tenant_id="acme",
                model_id="credit-risk-v3",
                action="predict",
                trace_id=f"trace-{index}",
                reasons=["concurrent append test"],
            )
        )
        return audit.append_to_chain(record, "acme")

    @pytest.mark.parametrize("workers", [8, 24])
    def test_parallel_appends_produce_an_intact_chain(self, tenant, workers):
        """No lost entries, no duplicate seq, and the chain still verifies."""
        count = workers * 4

        with ThreadPoolExecutor(max_workers=workers) as pool:
            hashes = list(pool.map(self._append, range(count)))

        assert len(set(hashes)) == count, "two appends produced the same entry hash"

        result = verify_chain("acme")
        assert result["valid"], result["detail"]
        assert result["entries"] == count, (
            f"{count} appends produced {result['entries']} entries — "
            "some were lost to the seq race"
        )

    def test_every_concurrent_append_is_retained(self, tenant):
        """Each trace_id written must be findable afterwards.

        A chain can verify perfectly and still be missing entries: dropping a
        write leaves the surviving links consistent with each other. Verifying
        the chain is therefore not enough — the count has to be checked against
        what was actually submitted.
        """
        from sqlalchemy import select

        from shared.db.models import AuditEntry
        from shared.db.session import session_scope

        count = 40
        with ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(self._append, range(count)))

        with session_scope() as db:
            entries = list(db.execute(select(AuditEntry).order_by(AuditEntry.seq)).scalars())

        assert [e.seq for e in entries] == list(range(1, count + 1)), (
            "sequence numbers are not dense"
        )
        assert {e.payload["trace_id"] for e in entries} == {f"trace-{i}" for i in range(count)}


class TestConcurrentEvaluations:
    """The full hot path with many requests in flight at once."""

    @staticmethod
    async def _hammer(app, count: int, concurrency: int) -> list[httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        semaphore = asyncio.Semaphore(concurrency)

        async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as client:

            async def one(index: int) -> httpx.Response:
                async with semaphore:
                    return await client.post(
                        "/v1/evaluate",
                        json={
                            "model_id": "credit-risk-v3",
                            "action": "predict",
                            "features": {"income": 50000.0 + index, "utilisation": 0.3},
                        },
                        headers=auth(),
                    )

            return list(await asyncio.gather(*(one(i) for i in range(count))))

    @pytest.mark.asyncio
    async def test_concurrent_requests_all_succeed(self, tenant, registered_model):
        responses = await self._hammer(create_app(), count=100, concurrency=32)

        assert all(r.status_code == 200 for r in responses)
        assert len({r.json()["trace_id"] for r in responses}) == 100

    @pytest.mark.asyncio
    async def test_concurrent_requests_stay_inside_a_sane_latency_ceiling(
        self, tenant, registered_model
    ):
        responses = await self._hammer(create_app(), count=100, concurrency=32)

        latencies = sorted(float(r.headers["X-Custos-Latency-Ms"]) for r in responses)
        p99 = latencies[int(0.99 * len(latencies)) - 1]
        assert p99 < LATENCY_CEILING_MS, (
            f"p99 handler latency {p99:.1f} ms under 32-way concurrency — "
            f"something expensive is on the hot path"
        )

    @pytest.mark.asyncio
    async def test_concurrent_decisions_all_reach_the_audit_chain(self, tenant, registered_model):
        """The decision is worthless if its evidence did not survive the load."""
        responses = await self._hammer(create_app(), count=60, concurrency=16)

        audit_ids = [r.json()["audit_id"] for r in responses]
        assert all(audit_ids), "some decisions came back with no audit_id"
        assert len(set(audit_ids)) == len(audit_ids), "duplicate audit entry hashes"

        result = verify_chain("acme")
        assert result["valid"], result["detail"]
        assert result["entries"] == 60
