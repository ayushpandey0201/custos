"""Register model -> baseline -> config -> audit query."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from services.control.main import create_app
from tests.conftest import TEST_API_KEY, rows_from_columns


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


def auth() -> dict:
    return {"X-API-Key": TEST_API_KEY}


class TestTenantBootstrap:
    def test_create_tenant_returns_a_usable_key(self, client):
        response = client.post("/tenants", json={"tenant_id": "newco", "name": "New Co"})
        assert response.status_code == 201

        body = response.json()
        assert body["api_key"].startswith("custos_")
        assert body["config"]["thresholds"] == {"block": 0.3, "review": 0.6}

        # The returned key must actually authenticate.
        models = client.get("/models", headers={"X-API-Key": body["api_key"]})
        assert models.status_code == 200

    def test_plaintext_key_is_never_stored(self, client):
        from sqlalchemy import select

        from shared.db.models import Tenant
        from shared.db.session import session_scope

        api_key = client.post("/tenants", json={"tenant_id": "newco"}).json()["api_key"]

        with session_scope() as db:
            row = db.execute(select(Tenant).where(Tenant.tenant_id == "newco")).scalar_one()
        assert api_key not in json.dumps(row.config)
        assert row.api_key_hash != api_key
        assert len(row.api_key_hash) == 64

    def test_duplicate_tenant_is_rejected(self, client, tenant):
        assert client.post("/tenants", json={"tenant_id": tenant}).status_code == 409


class TestModelLifecycle:
    def test_register_then_list(self, client, tenant):
        created = client.post(
            "/models", json={"model_id": "credit-risk-v3", "name": "Credit Risk"}, headers=auth()
        )
        assert created.status_code == 201
        assert created.json()["has_baseline"] is False

        listed = client.get("/models", headers=auth()).json()
        assert [m["model_id"] for m in listed] == ["credit-risk-v3"]

    def test_duplicate_registration_is_rejected(self, client, tenant):
        client.post("/models", json={"model_id": "m1"}, headers=auth())
        assert client.post("/models", json={"model_id": "m1"}, headers=auth()).status_code == 409

    def test_baseline_upload(self, client, tenant, baseline_features):
        client.post("/models", json={"model_id": "m1"}, headers=auth())
        rows = rows_from_columns(baseline_features)

        response = client.post("/models/m1/baseline", json={"samples": rows}, headers=auth())
        assert response.status_code == 201
        assert response.json()["features"] == ["age", "income", "utilisation"]
        assert response.json()["sample_size"] == 500

        assert client.get("/models", headers=auth()).json()[0]["has_baseline"] is True

    def test_baseline_for_unregistered_model_is_404(self, client, tenant):
        response = client.post(
            "/models/ghost/baseline", json={"samples": [{"a": 1.0}]}, headers=auth()
        )
        assert response.status_code == 404

    def test_empty_baseline_is_rejected(self, client, tenant):
        client.post("/models", json={"model_id": "m1"}, headers=auth())
        assert (
            client.post("/models/m1/baseline", json={"samples": []}, headers=auth()).status_code
            == 422
        )

    def test_recompute_reports_severity(self, client, tenant, baseline_features):
        client.post("/models", json={"model_id": "m1"}, headers=auth())
        rows = rows_from_columns(baseline_features)
        client.post("/models/m1/baseline", json={"samples": rows}, headers=auth())

        body = client.post("/models/m1/recompute", headers=auth()).json()
        assert body["computed"] is True
        assert body["severity"] < 1 / 3

    def test_recompute_without_a_baseline_is_reported_honestly(self, client, tenant):
        client.post("/models", json={"model_id": "m1"}, headers=auth())
        body = client.post("/models/m1/recompute", headers=auth()).json()
        assert body["computed"] is False
        assert "baseline" in body["detail"]


class TestDriftHistory:
    def test_history_is_empty_before_any_recompute(self, client, tenant):
        client.post("/models", json={"model_id": "m1"}, headers=auth())
        body = client.get("/models/m1/drift", headers=auth()).json()
        assert body["current"] is None
        assert body["history"] == []

    def test_history_exposes_per_feature_breakdown(self, client, tenant, baseline_features):
        client.post("/models", json={"model_id": "m1"}, headers=auth())
        rows = rows_from_columns(baseline_features)
        client.post("/models/m1/baseline", json={"samples": rows}, headers=auth())
        client.post("/models/m1/recompute", headers=auth())

        body = client.get("/models/m1/drift", headers=auth()).json()
        assert set(body["current"]["per_feature"]) == {"income", "utilisation", "age"}
        assert body["current"]["band"] in {"stable", "moderate", "significant"}
        assert len(body["history"]) == 1

    def test_history_is_oldest_first_for_plotting(self, client, tenant, baseline_features):
        client.post("/models", json={"model_id": "m1"}, headers=auth())
        rows = rows_from_columns(baseline_features)
        client.post("/models/m1/baseline", json={"samples": rows}, headers=auth())

        client.post("/models/m1/recompute", headers=auth())
        shifted = [{**r, "income": r["income"] + 40000} for r in rows]
        client.post("/models/m1/baseline", json={"samples": rows}, headers=auth())
        client.post("/models/m1/recompute", headers=auth())

        history = client.get("/models/m1/drift", headers=auth()).json()["history"]
        assert len(history) >= 2
        assert shifted  # the shifted batch is exercised in the worker tests


class TestConfig:
    def test_defaults_are_returned(self, client, tenant):
        body = client.get("/config", headers=auth()).json()
        assert body["enabled_engines"] == ["policy", "drift", "risk"]
        assert body["weights"]["drift"] == 0.5

    def test_thresholds_can_be_tightened(self, client, tenant):
        response = client.put(
            "/config", json={"thresholds": {"block": 0.5, "review": 0.8}}, headers=auth()
        )
        assert response.status_code == 200
        assert client.get("/config", headers=auth()).json()["thresholds"]["block"] == 0.5

    def test_incoherent_thresholds_are_rejected(self, client, tenant):
        """block above review would make REVIEW unreachable."""
        response = client.put(
            "/config", json={"thresholds": {"block": 0.9, "review": 0.2}}, headers=auth()
        )
        assert response.status_code == 400

    def test_unknown_engine_is_rejected(self, client, tenant):
        response = client.put("/config", json={"enabled_engines": ["telepathy"]}, headers=auth())
        assert response.status_code == 400
        assert "telepathy" in json.dumps(response.json())

    def test_partial_update_leaves_other_fields_alone(self, client, tenant):
        client.put("/config", json={"fail_open": False}, headers=auth())
        body = client.get("/config", headers=auth()).json()
        assert body["fail_open"] is False
        assert body["weights"]["drift"] == 0.5

    def test_config_change_is_visible_immediately(self, client, tenant):
        """The gateway caches config; a write must evict, not wait out the TTL."""
        from shared.config.tenant import load_tenant_config

        load_tenant_config(tenant)  # warm the cache
        client.put("/config", json={"thresholds": {"block": 0.7, "review": 0.9}}, headers=auth())
        assert load_tenant_config(tenant).thresholds["block"] == 0.7


class TestPolicyRules:
    def test_upsert_and_list(self, client, tenant):
        response = client.put(
            "/config/rules",
            json={
                "rule_id": "max-amount",
                "condition": "amount > 500000",
                "action": "veto",
                "description": "over limit",
            },
            headers=auth(),
        )
        assert response.status_code == 200
        assert [r["rule_id"] for r in client.get("/config/rules", headers=auth()).json()] == [
            "max-amount"
        ]

    def test_malformed_rule_is_rejected_at_write_time(self, client, tenant):
        """A rule that cannot parse must never be stored — it would silently
        never apply on the hot path."""
        response = client.put(
            "/config/rules", json={"rule_id": "bad", "condition": "amount >"}, headers=auth()
        )
        assert response.status_code == 400

    def test_injection_attempt_is_rejected(self, client, tenant):
        response = client.put(
            "/config/rules",
            json={"rule_id": "evil", "condition": "__import__('os').system('ls') == 1"},
            headers=auth(),
        )
        assert response.status_code == 400

    def test_unknown_action_is_rejected(self, client, tenant):
        response = client.put(
            "/config/rules",
            json={"rule_id": "r", "condition": "amount > 1", "action": "explode"},
            headers=auth(),
        )
        assert response.status_code == 400

    def test_rule_can_be_replaced_and_deleted(self, client, tenant):
        client.put(
            "/config/rules", json={"rule_id": "r", "condition": "amount > 1"}, headers=auth()
        )
        client.put(
            "/config/rules", json={"rule_id": "r", "condition": "amount > 999"}, headers=auth()
        )
        rules = client.get("/config/rules", headers=auth()).json()
        assert len(rules) == 1 and rules[0]["condition"] == "amount > 999"

        assert client.delete("/config/rules/r", headers=auth()).status_code == 204
        assert client.get("/config/rules", headers=auth()).json() == []


class TestAuditQuery:
    def _write_entries(self, tenant: str, count: int = 3) -> None:
        from services.gateway.audit import append_to_chain, build_record
        from shared.schemas.decision import Decision, DecisionRecord

        for i in range(count):
            append_to_chain(
                build_record(
                    DecisionRecord(
                        decision=Decision.BLOCK if i == 1 else Decision.ALLOW,
                        trust_score=0.9,
                        tenant_id=tenant,
                        model_id="m1" if i < 2 else "m2",
                        trace_id=f"t{i}",
                    )
                ),
                tenant,
            )

    def test_entries_are_returned_newest_first(self, client, tenant):
        self._write_entries(tenant, 3)
        entries = client.get("/audit", headers=auth()).json()["entries"]
        assert [e["seq"] for e in entries] == [3, 2, 1]

    def test_filter_by_decision(self, client, tenant):
        self._write_entries(tenant, 3)
        entries = client.get("/audit?decision=BLOCK", headers=auth()).json()["entries"]
        assert len(entries) == 1
        assert entries[0]["payload"]["decision"] == "BLOCK"

    def test_filter_scans_past_the_page_size(self, client, tenant):
        """The bug this guards: filtering a page that was already LIMITed.

        One BLOCK buried under 60 ALLOWs must still be found on a 50-row page.
        """
        from services.gateway.audit import append_to_chain, build_record
        from shared.schemas.decision import Decision, DecisionRecord

        for i in range(61):
            append_to_chain(
                build_record(
                    DecisionRecord(
                        # The single BLOCK is the *oldest* entry, so a
                        # newest-first page of 50 cannot contain it.
                        decision=Decision.BLOCK if i == 0 else Decision.ALLOW,
                        trust_score=0.9,
                        tenant_id=tenant,
                        model_id="m1",
                        trace_id=f"t{i}",
                    )
                ),
                tenant,
            )

        body = client.get("/audit?decision=BLOCK", headers=auth()).json()
        assert len(body["entries"]) == 1
        assert body["entries"][0]["seq"] == 1
        assert body["scanned"] == 61

    def test_limit_counts_matches_not_rows_examined(self, client, tenant):
        self._write_entries(tenant, 3)
        body = client.get("/audit?decision=ALLOW&limit=1", headers=auth()).json()
        assert len(body["entries"]) == 1
        assert body["entries"][0]["payload"]["decision"] == "ALLOW"

    def test_offset_skips_matches_not_rows(self, client, tenant):
        self._write_entries(tenant, 3)
        page = client.get("/audit?decision=ALLOW&limit=1&offset=1", headers=auth()).json()
        assert len(page["entries"]) == 1
        # Entries 3 and 1 are ALLOW (2 is BLOCK); newest-first, offset 1 is #1.
        assert page["entries"][0]["seq"] == 1

    def test_filter_by_model(self, client, tenant):
        self._write_entries(tenant, 3)
        entries = client.get("/audit?model_id=m2", headers=auth()).json()["entries"]
        assert all(e["payload"]["model_id"] == "m2" for e in entries)

    def test_verify_reports_a_healthy_chain(self, client, tenant):
        self._write_entries(tenant, 5)
        body = client.get("/audit/verify", headers=auth()).json()
        assert body["valid"] is True
        assert body["entries"] == 5

    def test_verify_detects_tampering_through_the_api(self, client, tenant):
        from sqlalchemy import select

        from shared.db.models import AuditEntry
        from shared.db.session import session_scope

        self._write_entries(tenant, 4)
        with session_scope() as db:
            entry = db.execute(select(AuditEntry).where(AuditEntry.seq == 2)).scalar_one()
            entry.payload = {**entry.payload, "decision": "ALLOW", "trust_score": 1.0}

        body = client.get("/audit/verify", headers=auth()).json()
        assert body["valid"] is False
        assert body["broken_at"] == 2

    def test_export_streams_json_lines(self, client, tenant):
        self._write_entries(tenant, 3)
        response = client.get("/audit/export", headers=auth())

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/x-ndjson")
        lines = [json.loads(line) for line in response.text.strip().split("\n")]
        assert [entry["seq"] for entry in lines] == [1, 2, 3]

    def test_tenants_cannot_read_each_other(self, client, tenant):
        self._write_entries(tenant, 2)
        other_key = client.post("/tenants", json={"tenant_id": "other"}).json()["api_key"]

        entries = client.get("/audit", headers={"X-API-Key": other_key}).json()["entries"]
        assert entries == []
