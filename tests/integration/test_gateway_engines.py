"""Gateway <-> engines <-> db round-trip."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.gateway.main import create_app
from shared.schemas.decision import Decision
from tests.conftest import TEST_API_KEY, rows_from_columns


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


def auth(key: str = TEST_API_KEY) -> dict:
    return {"X-API-Key": key}


def evaluate(client, **body) -> dict:
    payload = {"model_id": "credit-risk-v3", "action": "predict", **body}
    response = client.post("/v1/evaluate", json=payload, headers=auth())
    assert response.status_code == 200, response.text
    return response.json()


class TestAuthentication:
    def test_missing_key_is_rejected(self, client, tenant):
        assert client.post("/v1/evaluate", json={"model_id": "m"}).status_code == 401

    def test_invalid_key_is_rejected(self, client, tenant):
        response = client.post("/v1/evaluate", json={"model_id": "m"}, headers=auth("nope"))
        assert response.status_code == 401

    def test_valid_key_resolves_the_tenant(self, client, tenant, registered_model):
        assert evaluate(client)["decision"] in {d.value for d in Decision}


class TestDecisionFlow:
    def test_unregistered_model_routes_to_review(self, client, tenant):
        """ADR 0005, end to end through the real HTTP surface."""
        body = evaluate(client, model_id="never-registered")
        assert body["decision"] == "REVIEW"
        assert any("not registered" in r for r in body["reasons"])

    def test_registering_a_model_takes_effect_immediately(self, client, tenant):
        """The gateway caches the 'unknown model' result; registration must evict it.

        Without invalidation a model registered a second ago keeps routing to
        REVIEW for the whole TTL — which would break the very first thing an
        operator does after registering.
        """
        from shared.db.models import Model
        from shared.db.registry import invalidate_model_registration
        from shared.db.session import session_scope

        # Warm the negative cache entry.
        assert evaluate(client, model_id="late-model")["decision"] == "REVIEW"

        with session_scope() as db:
            db.add(Model(tenant_id=tenant, model_id="late-model", name="Late"))
        invalidate_model_registration(tenant, "late-model")

        body = evaluate(client, model_id="late-model")
        assert not any("not registered" in r for r in body["reasons"])

    def test_registered_model_without_drift_data_is_degraded(
        self, client, tenant, registered_model
    ):
        """No baseline yet: degraded, not blocked and not silently allowed."""
        body = evaluate(client)
        assert "drift" in body["degraded_engines"]
        assert body["signals"]["drift"]["detail"]["reason"] == "no_drift_snapshot"

    def test_all_engines_degraded_routes_to_review(self, client, tenant, registered_model):
        body = evaluate(client)
        assert set(body["degraded_engines"]) == {"policy", "drift", "risk"}
        assert body["decision"] == "REVIEW"

    def test_policy_veto_blocks(self, client, tenant, registered_model, veto_rule):
        body = evaluate(client, action="disburse", context={"amount": 900000})
        assert body["decision"] == "BLOCK"
        assert body["trust_score"] == 0.0
        assert any("manual authorisation" in r for r in body["reasons"])

    def test_policy_rule_that_does_not_match_allows(
        self, client, tenant, registered_model, veto_rule
    ):
        body = evaluate(client, action="disburse", context={"amount": 1000})
        assert body["decision"] == "ALLOW"
        assert body["trust_score"] == pytest.approx(1.0)

    def test_response_carries_a_trace_id_and_audit_id(
        self, client, tenant, registered_model, veto_rule
    ):
        body = evaluate(client, context={"amount": 1})
        assert body["trace_id"]
        assert body["audit_id"] and len(body["audit_id"]) == 64

    def test_every_decision_has_a_reason(self, client, tenant, registered_model):
        assert evaluate(client)["reasons"]


class TestDriftIntegration:
    def _seed(self, client, tenant, model_id, baseline_features, shift):
        """Register, baseline, feed a live window, recompute."""
        from engines.drift import worker
        from shared.db.models import FeatureSample, Model
        from shared.db.session import session_scope

        with session_scope() as db:
            db.add(Model(tenant_id=tenant, model_id=model_id, name=model_id))

        rows = rows_from_columns(baseline_features)
        worker.build_baseline(tenant, model_id, samples=rows)

        live = [{k: v + shift.get(k, 0.0) for k, v in row.items()} for row in rows]
        with session_scope() as db:
            for row in live:
                db.add(FeatureSample(tenant_id=tenant, model_id=model_id, features=row))

        return worker.recompute_drift(tenant, model_id)

    def test_stable_traffic_allows(self, client, tenant, baseline_features):
        self._seed(client, tenant, "stable-model", baseline_features, shift={})
        body = evaluate(client, model_id="stable-model")
        assert body["decision"] == "ALLOW"
        assert body["signals"]["drift"]["detail"]["band"] == "stable"

    def test_severe_drift_drives_the_decision_down(self, client, tenant, baseline_features):
        """A large shift in the heaviest-weighted signal must change the verdict."""
        result = self._seed(
            client, tenant, "drifted-model", baseline_features, shift={"income": 40000}
        )
        assert result["severity"] > 0.3

        body = evaluate(client, model_id="drifted-model")
        assert body["decision"] in {"REVIEW", "BLOCK"}
        assert body["signals"]["drift"]["score"] < 0.7
        assert body["signals"]["drift"]["detail"]["top_features"][0]["feature"] == "income"

    def test_drift_signal_names_the_responsible_feature(self, client, tenant, baseline_features):
        self._seed(client, tenant, "attrib-model", baseline_features, shift={"utilisation": 0.5})
        body = evaluate(client, model_id="attrib-model")
        top = body["signals"]["drift"]["detail"]["top_features"][0]
        assert top["feature"] == "utilisation"


class TestFeatureCapture:
    def test_features_are_persisted_for_the_next_recompute(self, client, tenant, registered_model):
        from sqlalchemy import select

        from shared.db.models import FeatureSample
        from shared.db.session import session_scope

        evaluate(client, features={"income": 55000.0, "utilisation": 0.4})

        with session_scope() as db:
            rows = list(db.execute(select(FeatureSample)).scalars())
        assert len(rows) == 1
        assert rows[0].features["income"] == 55000.0


class TestOperational:
    def test_health_reports_engines_and_database(self, client):
        body = client.get("/health").json()
        assert body["status"] == "ok"
        assert body["database"] == "up"
        assert set(body["engines"]) == {"policy", "drift", "risk"}

    def test_metrics_count_decisions(self, client, tenant, registered_model):
        evaluate(client)
        text = client.get("/metrics").text
        assert "custos_decisions_total" in text
        assert "custos_latency_ms" in text

    def test_latency_header_is_present(self, client, tenant, registered_model):
        response = client.post("/v1/evaluate", json={"model_id": "credit-risk-v3"}, headers=auth())
        assert float(response.headers["X-Custos-Latency-Ms"]) >= 0
