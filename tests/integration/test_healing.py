"""Governed self-healing, end to end through the real gateway and control plane.

Three properties are the point of the design, and each has a test here:

  1. No repair changes a verdict until a named person approves it.
  2. A repair whose shadow test failed cannot be approved.
  3. Every step lands on the tenant's hash chain, and the chain still verifies.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.control.main import create_app as control_app
from services.gateway.main import create_app as gateway_app
from tests.conftest import TEST_API_KEY

MODEL = "credit-risk-v3"
POPULATION = {
    "income": (60000.0, 15000.0),
    "utilisation": (0.35, 0.12),
    "bureau_score": (720.0, 60.0),
    "months_employed": (48.0, 24.0),
}
AUTH = {"X-API-Key": TEST_API_KEY}
REVIEWER = {"approver": "Dr. S. Reviewer", "note": "checked with the data team"}


def applicants(rng, n, shift=None, pin=None):
    shift, pin = shift or {}, pin or {}
    rows = []
    for _ in range(n):
        row = {k: rng.gauss(mu, sd) + shift.get(k, 0.0) for k, (mu, sd) in POPULATION.items()}
        row.update(pin)
        rows.append(row)
    return rows


@pytest.fixture
def control():
    with TestClient(control_app()) as c:
        yield c


@pytest.fixture
def gateway():
    with TestClient(gateway_app()) as c:
        yield c


@pytest.fixture
def model(control, tenant, rng):
    control.post("/models", json={"model_id": MODEL, "name": "Credit Risk"}, headers=AUTH)
    control.post(f"/models/{MODEL}/baseline", json={"samples": applicants(rng, 600)}, headers=AUTH)
    return MODEL


def traffic(gateway, rows) -> list[dict]:
    """Real requests through the real gateway: decisions logged, features captured."""
    out = []
    for row in rows:
        response = gateway.post(
            "/v1/evaluate",
            json={"model_id": MODEL, "action": "predict", "features": row},
            headers=AUTH,
        )
        assert response.status_code == 200, response.text
        out.append(response.json())
    return out


def scan(control) -> dict:
    response = control.post(f"/healing/scan/{MODEL}", headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


def proposal(incident: dict, action: str) -> dict:
    return next(r for r in incident["remediations"] if r["action"] == action)


def healing_events(control) -> list[dict]:
    entries = control.get("/audit?limit=500", headers=AUTH).json()["entries"]
    return [e["payload"] for e in reversed(entries) if e["payload"].get("type") == "healing"]


def quarantined(body: dict) -> bool:
    return any("quarantined" in r for r in body["reasons"])


@pytest.fixture
def broken_feed(control, gateway, model, rng):
    """Healthy traffic, then the bureau-score feed dies and pins to 720."""
    # Enough healthy traffic that sampling noise reads as stable, not moderate.
    traffic(gateway, applicants(rng, 200))
    control.post(f"/models/{MODEL}/recompute", headers=AUTH)  # drift is live
    traffic(gateway, applicants(rng, 200, pin={"bureau_score": 720.0}))
    return scan(control)["incident"]


class TestDetection:
    def test_healthy_traffic_opens_nothing(self, control, gateway, model, rng):
        traffic(gateway, applicants(rng, 200))
        body = scan(control)
        assert body["incident"] is None
        assert body["diagnosis"]["kind"] == "healthy"

    def test_a_broken_feed_is_diagnosed_as_one(self, broken_feed):
        assert broken_feed["kind"] == "pipeline_break"
        assert "bureau_score" in broken_feed["summary"]
        assert [r["action"] for r in broken_feed["remediations"]] == ["quarantine_input"]

    def test_rebaselining_on_a_broken_feed_is_withheld_and_says_why(self, broken_feed):
        withheld = broken_feed["diagnosis"]["withheld"]
        assert withheld[0]["action"] == "rebaseline"
        assert "broken data look normal" in withheld[0]["why"]

    def test_the_shadow_test_measures_impact_on_real_decisions(self, broken_feed):
        impact = proposal(broken_feed, "quarantine_input")["shadow"]["impact"]
        assert impact["replayed"] >= 200
        assert impact["changed"] > 0
        assert set(impact["transitions"]) <= {"ALLOW→REVIEW"}

    def test_scanning_again_does_not_open_a_duplicate(self, control, broken_feed):
        again = scan(control)
        assert again["new"] is False
        assert again["incident"]["id"] == broken_feed["id"]
        assert len(control.get("/healing/incidents", headers=AUTH).json()) == 1

    def test_every_recompute_runs_detection(self, control, gateway, model, rng):
        traffic(gateway, applicants(rng, 200, pin={"bureau_score": 720.0}))
        body = control.post(f"/models/{MODEL}/recompute", headers=AUTH).json()
        assert body["healing"]["kind"] == "pipeline_break"
        assert body["healing"]["new"] is True


class TestHumanGovernance:
    def test_nothing_changes_before_a_person_approves(self, gateway, broken_feed, rng):
        """Property 1. Detection and proposal alone must not touch a single verdict."""
        body = traffic(gateway, applicants(rng, 1))[0]
        assert not quarantined(body)

    def test_an_approval_must_name_a_person(self, control, broken_feed):
        rid = proposal(broken_feed, "quarantine_input")["id"]
        assert (
            control.post(
                f"/healing/remediations/{rid}/approve", json={"approver": ""}, headers=AUTH
            ).status_code
            == 422
        )
        assert (
            control.post(
                f"/healing/remediations/{rid}/approve", json={"approver": "   "}, headers=AUTH
            ).status_code
            == 409
        )

    def test_approved_quarantine_holds_decisions_immediately(
        self, control, gateway, broken_feed, rng
    ):
        rid = proposal(broken_feed, "quarantine_input")["id"]
        approved = control.post(f"/healing/remediations/{rid}/approve", json=REVIEWER, headers=AUTH)
        assert approved.status_code == 200
        assert proposal(approved.json(), "quarantine_input")["status"] == "applied"

        body = traffic(gateway, applicants(rng, 1))[0]
        assert body["decision"] == "REVIEW"
        assert quarantined(body)
        assert any("bureau_score" in r for r in body["reasons"])

    def test_a_proposal_cannot_be_approved_twice(self, control, broken_feed):
        rid = proposal(broken_feed, "quarantine_input")["id"]
        control.post(f"/healing/remediations/{rid}/approve", json=REVIEWER, headers=AUTH)
        again = control.post(f"/healing/remediations/{rid}/approve", json=REVIEWER, headers=AUTH)
        assert again.status_code == 409

    def test_a_rejection_is_recorded_and_changes_nothing(self, control, gateway, broken_feed, rng):
        rid = proposal(broken_feed, "quarantine_input")["id"]
        rejected = control.post(f"/healing/remediations/{rid}/reject", json=REVIEWER, headers=AUTH)
        assert proposal(rejected.json(), "quarantine_input")["status"] == "rejected"
        assert not quarantined(traffic(gateway, applicants(rng, 1))[0])
        events = [e["event"] for e in healing_events(control)]
        assert events[-1] == "remediation_rejected"

    def test_an_incident_cannot_be_closed_under_an_active_quarantine(self, control, broken_feed):
        rid = proposal(broken_feed, "quarantine_input")["id"]
        control.post(f"/healing/remediations/{rid}/approve", json=REVIEWER, headers=AUTH)
        closed = control.post(
            f"/healing/incidents/{broken_feed['id']}/close", json=REVIEWER, headers=AUTH
        )
        assert closed.status_code == 409
        assert "release" in closed.json()["detail"]

    def test_another_tenant_cannot_touch_the_incident(self, control, broken_feed):
        other = control.post("/tenants", json={"tenant_id": "rival", "name": "Rival"}).json()
        rid = proposal(broken_feed, "quarantine_input")["id"]
        response = control.post(
            f"/healing/remediations/{rid}/approve",
            json=REVIEWER,
            headers={"X-API-Key": other["api_key"]},
        )
        assert response.status_code == 404
        assert (
            control.get("/healing/incidents", headers={"X-API-Key": other["api_key"]}).json() == []
        )


class TestFullRepairLoop:
    def test_break_quarantine_repair_verify_release(self, control, gateway, broken_feed, rng):
        rid = proposal(broken_feed, "quarantine_input")["id"]
        control.post(f"/healing/remediations/{rid}/approve", json=REVIEWER, headers=AUTH)

        # Still broken: verification changes nothing and records nothing.
        traffic(gateway, applicants(rng, 50, pin={"bureau_score": 720.0}))
        before = len(healing_events(control))
        assert scan(control)["verification"] == "unchanged"
        assert len(healing_events(control)) == before

        # The data team fixes the feed.
        traffic(gateway, applicants(rng, 200))
        verified = scan(control)
        assert verified["verification"] == "release_proposed"
        release = proposal(verified["incident"], "release_input")
        assert release["shadow"]["passed"] is True
        assert release["shadow"]["impact"]["changed"] > 0  # held decisions would be freed

        # Releasing needs a person too.
        assert quarantined(traffic(gateway, applicants(rng, 1))[0])
        done = control.post(
            f"/healing/remediations/{release['id']}/approve", json=REVIEWER, headers=AUTH
        ).json()
        assert done["status"] == "resolved"
        assert proposal(done, "quarantine_input")["status"] == "released"
        after = traffic(gateway, applicants(rng, 1))[0]
        assert not quarantined(after)
        # The broken period no longer counts as drift: measured from the
        # verified-healthy traffic, the model is trusted again straight away.
        assert after["signals"]["drift"]["detail"]["band"] == "stable"
        assert after["decision"] == "ALLOW"

    def test_every_step_is_on_the_chain_and_the_chain_verifies(
        self, control, gateway, broken_feed, rng
    ):
        """Property 3."""
        rid = proposal(broken_feed, "quarantine_input")["id"]
        control.post(f"/healing/remediations/{rid}/approve", json=REVIEWER, headers=AUTH)
        traffic(gateway, applicants(rng, 200))
        release = proposal(scan(control)["incident"], "release_input")
        control.post(f"/healing/remediations/{release['id']}/approve", json=REVIEWER, headers=AUTH)

        events = healing_events(control)
        assert [e["event"] for e in events] == [
            "incident_opened",
            "remediation_proposed",
            "remediation_approved",
            "remediation_applied",
            "verified",
            "remediation_proposed",
            "remediation_approved",
            "remediation_applied",
        ]
        approvals = [e for e in events if e["event"] == "remediation_approved"]
        assert {e["actor"] for e in approvals} == {"Dr. S. Reviewer"}
        assert approvals[0]["detail"]["note"] == "checked with the data team"

        chain = control.get("/audit/verify", headers=AUTH).json()
        assert chain["valid"] is True

    def test_healing_events_do_not_pollute_decision_filters(self, control, gateway, broken_feed):
        entries = control.get("/audit?decision=REVIEW&limit=500", headers=AUTH).json()["entries"]
        assert all(e["payload"].get("type") != "healing" for e in entries)


@pytest.fixture
def shifted(control, gateway, model, rng):
    """A settled population shift: incomes fall, utilisation climbs."""
    traffic(gateway, applicants(rng, 400, shift={"income": -30000, "utilisation": 0.4}))
    return scan(control)["incident"]


class TestPopulationShift:
    def test_a_shift_offers_rebaseline_or_retrain_and_nothing_else(self, shifted):
        assert shifted["kind"] == "population_shift"
        assert [r["action"] for r in shifted["remediations"]] == ["rebaseline", "request_retrain"]
        assert shifted["diagnosis"]["withheld"] == []

    def test_a_settled_shift_passes_the_hold_out_test(self, shifted):
        rebaseline = proposal(shifted, "rebaseline")
        assert rebaseline["shadow"]["passed"] is True
        assert "settled" in rebaseline["shadow"]["checks"][0]

    def test_rebaselining_is_applied_undoable_and_resolves_once_verified(
        self, control, gateway, shifted, rng
    ):
        from sqlalchemy import select

        from shared.db.models import Model, Remediation
        from shared.db.session import session_scope

        with session_scope() as db:
            original = db.execute(
                select(Model.baseline).where(Model.model_id == MODEL)
            ).scalar_one()

        rid = proposal(shifted, "rebaseline")["id"]
        after = control.post(f"/healing/remediations/{rid}/approve", json=REVIEWER, headers=AUTH)
        body = after.json()
        assert proposal(body, "rebaseline")["status"] == "applied"
        assert proposal(body, "request_retrain")["status"] == "superseded"

        with session_scope() as db:
            current = db.execute(select(Model.baseline).where(Model.model_id == MODEL)).scalar_one()
            undo = db.get(Remediation, rid).undo
        assert current != original
        assert undo["baseline"] == original

        # Nothing is measured against the new reference yet, so verification
        # has nothing to go on — the traffic it was built from does not count.
        assert scan(control)["verification"] == "unchanged"

        traffic(gateway, applicants(rng, 200, shift={"income": -30000, "utilisation": 0.4}))
        assert scan(control)["verification"] == "resolved"

        # The drift floor lifts: the new population is the reference now.
        decision = traffic(
            gateway, applicants(rng, 1, shift={"income": -30000, "utilisation": 0.4})
        )[0]
        assert decision["signals"]["drift"]["detail"]["band"] != "significant"

    def test_a_failed_rebaseline_proposes_a_rollback(self, control, gateway, shifted, rng):
        from sqlalchemy import select

        from shared.db.models import Model
        from shared.db.session import session_scope

        with session_scope() as db:
            original = db.execute(
                select(Model.baseline).where(Model.model_id == MODEL)
            ).scalar_one()

        rid = proposal(shifted, "rebaseline")["id"]
        control.post(f"/healing/remediations/{rid}/approve", json=REVIEWER, headers=AUTH)

        # The population keeps moving, past the new reference too.
        traffic(gateway, applicants(rng, 200, shift={"income": -60000, "utilisation": 0.9}))
        verified = scan(control)
        assert verified["verification"] == "rollback_proposed"
        assert proposal(verified["incident"], "rebaseline")["status"] == "failed_verification"

        rollback = proposal(verified["incident"], "rollback_baseline")
        done = control.post(
            f"/healing/remediations/{rollback['id']}/approve", json=REVIEWER, headers=AUTH
        ).json()
        assert proposal(done, "rebaseline")["status"] == "rolled_back"
        with session_scope() as db:
            restored = db.execute(
                select(Model.baseline).where(Model.model_id == MODEL)
            ).scalar_one()
        assert restored == original
        # With the reference restored, retraining is back on the table.
        assert [r["status"] for r in done["remediations"] if r["action"] == "request_retrain"][
            -1
        ] == ("proposed")


class TestShadowGate:
    def test_a_population_still_moving_cannot_be_rebaselined(self, control, gateway, model, rng):
        """Property 2. The newer half of the window drifts from the older half."""
        traffic(gateway, applicants(rng, 200, shift={"income": -20000, "utilisation": 0.25}))
        traffic(gateway, applicants(rng, 200, shift={"income": -50000, "utilisation": 0.7}))
        incident = scan(control)["incident"]
        rebaseline = proposal(incident, "rebaseline")
        assert rebaseline["shadow"]["passed"] is False
        assert "still moving" in rebaseline["shadow"]["checks"][0]

        response = control.post(
            f"/healing/remediations/{rebaseline['id']}/approve", json=REVIEWER, headers=AUTH
        )
        assert response.status_code == 409
        assert "failed its shadow test" in response.json()["detail"]

    def test_a_feed_that_breaks_mid_incident_blocks_rebaselining(
        self, control, gateway, shifted, rng
    ):
        """The guard re-runs on retest: what gets approved is what was last tested."""
        traffic(
            gateway,
            applicants(
                rng, 400, shift={"income": -30000, "utilisation": 0.4}, pin={"bureau_score": 0.0}
            ),
        )
        rid = proposal(shifted, "rebaseline")["id"]
        retested = control.post(f"/healing/remediations/{rid}/retest", headers=AUTH).json()
        shadow = proposal(retested, "rebaseline")["shadow"]
        assert shadow["passed"] is False
        assert "broken input" in shadow["checks"][0]
        assert (
            control.post(
                f"/healing/remediations/{rid}/approve", json=REVIEWER, headers=AUTH
            ).status_code
            == 409
        )


def test_the_candidate_reference_is_not_returned_in_full(control, shifted):
    """Hundreds of numbers per input belong in the database, not in every list response."""
    params = proposal(shifted, "rebaseline")["params"]
    assert all(isinstance(v, int) for v in params["baseline"].values())
