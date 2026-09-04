"""Ingest -> drift scores -> evaluate -> audit write -> verify chain.

The one test that exercises both planes together the way an operator actually
uses them. If this passes, the system does the thing it claims to do.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.control.main import create_app as create_control_app
from services.gateway.main import create_app as create_gateway_app
from tests.conftest import normal_sample, rows_from_columns


@pytest.fixture
def control():
    with TestClient(create_control_app()) as c:
        yield c


@pytest.fixture
def gateway():
    with TestClient(create_gateway_app()) as c:
        yield c


def test_full_lifecycle(control, gateway, rng):
    """Register, baseline, run clean traffic, drift the population, watch the
    verdict change, then prove the whole history is tamper-evident."""

    # --- 1. Bootstrap a tenant ------------------------------------------
    created = control.post("/tenants", json={"tenant_id": "lender", "name": "Lender Co"})
    assert created.status_code == 201
    api_key = created.json()["api_key"]
    headers = {"X-API-Key": api_key}

    # --- 2. An unregistered model is not silently allowed (ADR 0005) -----
    early = gateway.post(
        "/v1/evaluate", json={"model_id": "credit-risk-v3"}, headers=headers
    ).json()
    assert early["decision"] == "REVIEW"
    assert any("not registered" in r for r in early["reasons"])

    # --- 3. Register the model ------------------------------------------
    assert (
        control.post(
            "/models",
            json={"model_id": "credit-risk-v3", "name": "Credit Risk", "version": "3"},
            headers=headers,
        ).status_code
        == 201
    )

    # --- 4. A registered model with no baseline is degraded, not trusted --
    no_baseline = gateway.post(
        "/v1/evaluate", json={"model_id": "credit-risk-v3"}, headers=headers
    ).json()
    assert "drift" in no_baseline["degraded_engines"]
    assert no_baseline["decision"] == "REVIEW"

    # --- 5. Capture the training-time reference distribution -------------
    baseline_rows = rows_from_columns(
        {
            "income": normal_sample(rng, 60000, 15000, 600),
            "utilisation": normal_sample(rng, 0.35, 0.12, 600),
            "bureau_score": normal_sample(rng, 720, 60, 600),
        }
    )
    assert (
        control.post(
            "/models/credit-risk-v3/baseline", json={"samples": baseline_rows}, headers=headers
        ).status_code
        == 201
    )

    # --- 6. Healthy traffic -> stable drift -> ALLOW ----------------------
    for row in baseline_rows[:200]:
        gateway.post(
            "/v1/evaluate",
            json={"model_id": "credit-risk-v3", "action": "score", "features": row},
            headers=headers,
        )

    stable = control.post("/models/credit-risk-v3/recompute", headers=headers).json()
    assert stable["computed"] is True
    assert stable["severity"] < 1 / 3

    healthy = gateway.post(
        "/v1/evaluate",
        json={"model_id": "credit-risk-v3", "action": "score", "features": baseline_rows[0]},
        headers=headers,
    ).json()
    assert healthy["decision"] == "ALLOW"
    assert healthy["signals"]["drift"]["detail"]["band"] == "stable"

    # --- 7. The population shifts ----------------------------------------
    # Incomes collapse and utilisation spikes — a recession, or a broken
    # upstream feed. Custos cannot tell which; it can tell that the model is
    # no longer scoring the population it was trained on.
    drifted_rows = rows_from_columns(
        {
            "income": normal_sample(rng, 24000, 9000, 400),
            "utilisation": normal_sample(rng, 0.80, 0.10, 400),
            "bureau_score": normal_sample(rng, 715, 60, 400),
        }
    )
    for row in drifted_rows:
        gateway.post(
            "/v1/evaluate",
            json={"model_id": "credit-risk-v3", "action": "score", "features": row},
            headers=headers,
        )

    drifted = control.post("/models/credit-risk-v3/recompute", headers=headers).json()
    assert drifted["severity"] > stable["severity"]
    assert drifted["severity"] > 1 / 3

    # --- 8. The verdict changes without anyone touching config ------------
    after = gateway.post(
        "/v1/evaluate",
        json={"model_id": "credit-risk-v3", "action": "score", "features": drifted_rows[0]},
        headers=headers,
    ).json()
    assert after["decision"] in {"REVIEW", "BLOCK"}
    assert after["trust_score"] < healthy["trust_score"]

    # The signal names the responsible features, not just a number.
    top = [f["feature"] for f in after["signals"]["drift"]["detail"]["top_features"]]
    assert "income" in top or "utilisation" in top
    # bureau_score did not move, so it must not be blamed.
    assert top[0] != "bureau_score"

    # --- 9. A policy veto overrides everything ----------------------------
    control.put(
        "/config/rules",
        json={
            "rule_id": "max-disbursement",
            "condition": 'action == "disburse" and amount > 500000',
            "action": "veto",
            "description": "disbursements above 500000 require manual authorisation",
        },
        headers=headers,
    )
    vetoed = gateway.post(
        "/v1/evaluate",
        json={
            "model_id": "credit-risk-v3",
            "action": "disburse",
            "context": {"amount": 900000},
            "features": baseline_rows[0],
        },
        headers=headers,
    ).json()
    assert vetoed["decision"] == "BLOCK"
    assert vetoed["trust_score"] == 0.0
    assert any("manual authorisation" in r for r in vetoed["reasons"])

    # --- 10. Every decision landed in the audit chain ---------------------
    audit = control.get("/audit", headers=headers).json()["entries"]
    assert len(audit) > 0
    assert audit[0]["payload"]["decision"] == "BLOCK"

    verified = control.get("/audit/verify", headers=headers).json()
    assert verified["valid"] is True
    assert verified["entries"] >= 600

    # --- 11. Evidence export is complete and ordered ----------------------
    export = control.get("/audit/export", headers=headers)
    assert export.status_code == 200
    assert len(export.text.strip().split("\n")) == verified["entries"]

    # --- 12. Tampering with history is detectable -------------------------
    from sqlalchemy import select

    from shared.db.models import AuditEntry
    from shared.db.session import session_scope

    with session_scope() as db:
        entry = db.execute(
            select(AuditEntry).where(AuditEntry.tenant_id == "lender", AuditEntry.seq == 5)
        ).scalar_one()
        entry.payload = {**entry.payload, "decision": "ALLOW", "trust_score": 1.0}

    tampered = control.get("/audit/verify", headers=headers).json()
    assert tampered["valid"] is False
    assert tampered["broken_at"] == 5


def test_tenant_isolation_end_to_end(control, gateway, rng):
    """Two tenants sharing a deployment must never see each other's anything."""
    keys = {}
    for name in ("alpha", "beta"):
        keys[name] = control.post("/tenants", json={"tenant_id": name}).json()["api_key"]
        control.post("/models", json={"model_id": "shared-name"}, headers={"X-API-Key": keys[name]})

    # Same model_id, different tenants, different baselines.
    control.post(
        "/models/shared-name/baseline",
        json={"samples": rows_from_columns({"x": normal_sample(rng, 0, 1, 200)})},
        headers={"X-API-Key": keys["alpha"]},
    )

    alpha_models = control.get("/models", headers={"X-API-Key": keys["alpha"]}).json()
    beta_models = control.get("/models", headers={"X-API-Key": keys["beta"]}).json()
    assert alpha_models[0]["has_baseline"] is True
    assert beta_models[0]["has_baseline"] is False

    gateway.post(
        "/v1/evaluate", json={"model_id": "shared-name"}, headers={"X-API-Key": keys["alpha"]}
    )

    assert len(control.get("/audit", headers={"X-API-Key": keys["alpha"]}).json()["entries"]) == 1
    assert control.get("/audit", headers={"X-API-Key": keys["beta"]}).json()["entries"] == []


def test_fail_open_when_the_engine_layer_breaks(gateway, tenant, registered_model, monkeypatch):
    """ADR 0001: a Custos failure must not become the caller's failure."""

    async def explode(*args, **kwargs):
        raise RuntimeError("simulated engine layer failure")

    monkeypatch.setattr("services.gateway.trust_engine.evaluate", explode)

    body = gateway.post(
        "/v1/evaluate",
        json={"model_id": registered_model},
        headers={"X-API-Key": "test_key_abc123"},
    ).json()

    assert body["decision"] == "ALLOW"
    assert body["degraded_engines"] == ["*"]
    assert any("failed open" in r for r in body["reasons"])


def test_fail_closed_tenant_gets_503_instead(
    gateway, control, tenant, registered_model, monkeypatch
):
    """A tenant that opted out of fail-open must be told, not silently allowed."""
    control.put("/config", json={"fail_open": False}, headers={"X-API-Key": "test_key_abc123"})

    async def explode(*args, **kwargs):
        raise RuntimeError("simulated engine layer failure")

    monkeypatch.setattr("services.gateway.trust_engine.evaluate", explode)

    response = gateway.post(
        "/v1/evaluate",
        json={"model_id": registered_model},
        headers={"X-API-Key": "test_key_abc123"},
    )
    assert response.status_code == 503
