"""Guided-demo endpoints: off by default, and honest when the system is not ready.

The full seven-step run needs a live gateway and is exercised end to end
through the dashboard. These tests pin the properties that must hold without
one: the endpoints never ship enabled, steps refuse to run out of order, and a
stopped gateway produces a clear instruction instead of a fail-open verdict
that would make the demo quietly lie.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from services.control.main import create_app

# Nothing listens here, so the demo sees the gateway as down.
DEAD_GATEWAY = "http://127.0.0.1:9"


def test_demo_endpoints_are_off_by_default(monkeypatch):
    monkeypatch.delenv("CUSTOS_DEMO_MODE", raising=False)
    with TestClient(create_app()) as client:
        assert client.get("/demo/status").status_code == 404
        assert client.post("/demo/tamper").status_code == 404


def test_demo_endpoints_mount_only_when_asked():
    with TestClient(create_app(demo=True, demo_gateway_url=DEAD_GATEWAY)) as client:
        body = client.get("/demo/status").json()
    assert body == {"gateway": False, "control": True, "run": None}


def test_steps_refuse_to_run_before_start():
    with TestClient(create_app(demo=True, demo_gateway_url=DEAD_GATEWAY)) as client:
        response = client.post("/demo/act/1")
    assert response.status_code == 409
    assert "Start the demo first" in response.json()["detail"]


def test_tamper_refuses_before_the_story_reaches_it():
    with TestClient(create_app(demo=True, demo_gateway_url=DEAD_GATEWAY)) as client:
        assert client.post("/demo/tamper").status_code == 409


def test_a_stopped_gateway_gives_an_instruction_not_a_fake_verdict():
    """Fail-open would turn every step into APPROVED. The demo must say why instead."""
    with TestClient(create_app(demo=True, demo_gateway_url=DEAD_GATEWAY)) as client:
        response = client.post("/demo/start")
    assert response.status_code == 503
    assert "./app.sh" in response.json()["detail"]


def test_unknown_step_numbers_are_rejected():
    with TestClient(create_app(demo=True, demo_gateway_url=DEAD_GATEWAY)) as client:
        assert client.post("/demo/act/9").status_code == 404


class TestSelfHealingDemo:
    def test_off_by_default(self, monkeypatch):
        monkeypatch.delenv("CUSTOS_DEMO_MODE", raising=False)
        with TestClient(create_app()) as client:
            assert client.post("/demo/healing/start").status_code == 404

    def test_steps_refuse_to_run_before_start(self):
        with TestClient(create_app(demo=True, demo_gateway_url=DEAD_GATEWAY)) as client:
            response = client.post("/demo/healing/step/1", json={})
        assert response.status_code == 409
        assert "Start the self-healing demo first" in response.json()["detail"]

    def test_a_stopped_gateway_gives_an_instruction(self):
        with TestClient(create_app(demo=True, demo_gateway_url=DEAD_GATEWAY)) as client:
            response = client.post("/demo/healing/start")
        assert response.status_code == 503
        assert "./app.sh" in response.json()["detail"]

    def test_unknown_steps_are_rejected(self):
        with TestClient(create_app(demo=True, demo_gateway_url=DEAD_GATEWAY)) as client:
            assert client.post("/demo/healing/step/9", json={}).status_code == 404

    def test_status_reports_no_run(self):
        with TestClient(create_app(demo=True, demo_gateway_url=DEAD_GATEWAY)) as client:
            body = client.get("/demo/healing/status").json()
        assert body == {"gateway": False, "run": None}
