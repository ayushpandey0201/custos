"""Chain integrity, tamper detection, chain verify endpoint.

The audit chain's only claim is that modification is *detectable*. These tests
attack the chain the way someone covering their tracks would — edit a payload,
swap two entries, delete one, forge a hash — and assert that verification
catches each and localises it.
"""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import select

from services.gateway.audit import (
    GENESIS_HASH,
    append_to_chain,
    build_record,
    canonical_json,
    compute_hash,
    verify_chain,
)
from shared.db.models import AuditEntry
from shared.db.session import session_scope
from shared.schemas.decision import Decision, DecisionRecord


def make_payload(n: int, tenant: str = "acme") -> dict:
    return build_record(
        DecisionRecord(
            decision=Decision.ALLOW,
            trust_score=0.9,
            tenant_id=tenant,
            model_id="credit-risk-v3",
            trace_id=f"trace-{n}",
            reasons=[f"reason {n}"],
        )
    )


def append_many(tenant: str, count: int) -> list[str]:
    return [append_to_chain(make_payload(i, tenant), tenant) for i in range(count)]


class TestCanonicalJson:
    def test_key_order_does_not_change_the_serialisation(self):
        assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})

    def test_hash_is_stable_across_key_order(self):
        assert compute_hash(GENESIS_HASH, {"b": 1, "a": 2}) == compute_hash(
            GENESIS_HASH, {"a": 2, "b": 1}
        )

    def test_hash_matches_the_documented_construction(self):
        payload = {"a": 1}
        expected = hashlib.sha256((GENESIS_HASH + canonical_json(payload)).encode()).hexdigest()
        assert compute_hash(GENESIS_HASH, payload) == expected

    def test_different_payloads_hash_differently(self):
        assert compute_hash(GENESIS_HASH, {"a": 1}) != compute_hash(GENESIS_HASH, {"a": 2})

    def test_same_payload_under_different_predecessors_hashes_differently(self):
        """Position in the chain is part of what an entry commits to."""
        assert compute_hash(GENESIS_HASH, {"a": 1}) != compute_hash("f" * 64, {"a": 1})


class TestChainConstruction:
    def test_first_entry_links_to_genesis(self, tenant):
        append_to_chain(make_payload(0), tenant)
        with session_scope() as db:
            entry = db.execute(select(AuditEntry)).scalar_one()
        assert entry.prev_hash == GENESIS_HASH
        assert entry.seq == 1

    def test_sequence_numbers_are_contiguous(self, tenant):
        append_many(tenant, 5)
        with session_scope() as db:
            seqs = [
                e.seq for e in db.execute(select(AuditEntry).order_by(AuditEntry.seq)).scalars()
            ]
        assert seqs == [1, 2, 3, 4, 5]

    def test_each_entry_links_to_its_predecessor(self, tenant):
        hashes = append_many(tenant, 4)
        with session_scope() as db:
            entries = list(db.execute(select(AuditEntry).order_by(AuditEntry.seq)).scalars())
        assert entries[0].prev_hash == GENESIS_HASH
        for previous, current in zip(entries, entries[1:], strict=False):
            assert current.prev_hash == previous.entry_hash
        assert [e.entry_hash for e in entries] == hashes

    def test_chains_are_isolated_per_tenant(self, tenant):
        from shared.db.models import Tenant

        with session_scope() as db:
            db.add(Tenant(tenant_id="other", name="Other", api_key_hash="x", config={}))

        append_many(tenant, 3)
        append_many("other", 2)

        assert verify_chain(tenant)["entries"] == 3
        assert verify_chain("other")["entries"] == 2

    def test_append_requires_a_tenant(self):
        with pytest.raises(ValueError):
            append_to_chain({"no": "tenant"})


class TestVerification:
    def test_empty_chain_is_valid(self, tenant):
        result = verify_chain(tenant)
        assert result["valid"] and result["entries"] == 0

    def test_untouched_chain_verifies(self, tenant):
        append_many(tenant, 10)
        result = verify_chain(tenant)
        assert result["valid"]
        assert result["entries"] == 10
        assert result["broken_at"] is None

    def test_editing_a_payload_is_detected_and_localised(self, tenant):
        append_many(tenant, 5)

        with session_scope() as db:
            entry = db.execute(select(AuditEntry).where(AuditEntry.seq == 3)).scalar_one()
            payload = dict(entry.payload)
            payload["decision"] = "ALLOW" if payload["decision"] == "BLOCK" else "BLOCK"
            entry.payload = payload

        result = verify_chain(tenant)
        assert not result["valid"]
        assert result["broken_at"] == 3
        assert "modified" in result["detail"]

    def test_flipping_a_single_score_digit_is_detected(self, tenant):
        """The realistic attack: quietly nudge a number, not rewrite a verdict."""
        append_many(tenant, 3)
        with session_scope() as db:
            entry = db.execute(select(AuditEntry).where(AuditEntry.seq == 2)).scalar_one()
            payload = dict(entry.payload)
            payload["trust_score"] = 0.900001
            entry.payload = payload

        assert verify_chain(tenant)["broken_at"] == 2

    def test_deleting_an_entry_is_detected(self, tenant):
        append_many(tenant, 5)
        with session_scope() as db:
            entry = db.execute(select(AuditEntry).where(AuditEntry.seq == 3)).scalar_one()
            db.delete(entry)

        result = verify_chain(tenant)
        assert not result["valid"]
        assert "sequence gap" in result["detail"]

    def test_forging_an_entry_hash_breaks_the_next_link(self, tenant):
        """Recomputing one entry's hash to match a doctored payload is not enough.

        The successor still commits to the *old* hash, so the tamper surfaces
        one position later. Covering it up means rewriting every entry after it.
        """
        append_many(tenant, 4)
        with session_scope() as db:
            entry = db.execute(select(AuditEntry).where(AuditEntry.seq == 2)).scalar_one()
            payload = dict(entry.payload)
            payload["trust_score"] = 0.1
            entry.payload = payload
            entry.entry_hash = compute_hash(entry.prev_hash, payload)

        result = verify_chain(tenant)
        assert not result["valid"]
        assert result["broken_at"] == 3
        assert "predecessor" in result["detail"]

    def test_appending_after_a_break_does_not_repair_it(self, tenant):
        append_many(tenant, 3)
        with session_scope() as db:
            entry = db.execute(select(AuditEntry).where(AuditEntry.seq == 1)).scalar_one()
            entry.payload = {"tampered": True}

        append_many(tenant, 2)
        assert verify_chain(tenant)["broken_at"] == 1


class TestBuildRecord:
    def test_record_carries_the_decision_and_its_justification(self):
        payload = build_record(
            DecisionRecord(
                decision=Decision.BLOCK,
                trust_score=0.12,
                tenant_id="acme",
                model_id="m1",
                reasons=["trust score below block threshold"],
                degraded_engines=["risk"],
            )
        )
        assert payload["decision"] == "BLOCK"
        assert payload["trust_score"] == pytest.approx(0.12)
        assert payload["reasons"] == ["trust score below block threshold"]
        assert payload["degraded_engines"] == ["risk"]

    def test_raw_features_are_not_written_to_the_chain(self):
        """Customer data must not be duplicated into an append-only log."""
        payload = build_record(
            DecisionRecord(
                decision=Decision.ALLOW, trust_score=1.0, tenant_id="acme", model_id="m1"
            ),
            context={"weights_applied": {"drift": 0.6}},
        )
        assert "features" not in payload
        assert payload["context"] == {"weights_applied": {"drift": 0.6}}
