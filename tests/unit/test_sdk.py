"""SDK: fail-open transport, verdict mapping, @guard and gate().

The SDK is the part of Custos that runs inside someone else's production
service. Its most important property is not that it works — it is that it
cannot take the caller down when Custos is unreachable (ADR 0001), which is
what most of this file tests.
"""

from __future__ import annotations

import importlib
import json
import urllib.error
import urllib.request

import custos
import pytest
from custos import Blocked, CustosClient, ReviewRequired, Verdict, enforce

# `custos.guard` is the decorator, which shadows the submodule of the same
# name — so reach the module through importlib rather than attribute access,
# or the reset below silently sets an attribute on the function object.
guard_module = importlib.import_module("custos.guard")


@pytest.fixture(autouse=True)
def reset_sdk_client():
    """The SDK holds a process-wide client; keep tests independent."""
    guard_module._client = None
    yield
    guard_module._client = None


def fake_transport(monkeypatch, payload: dict | None = None, raises: Exception | None = None):
    """Replace urlopen so no test touches the network."""

    class _Response:
        def __init__(self, body: bytes) -> None:
            self._body = body

        def read(self) -> bytes:
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    calls: list = []

    def _urlopen(request, timeout=None):
        calls.append({"request": request, "timeout": timeout})
        if raises is not None:
            raise raises
        return _Response(json.dumps(payload or {}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    return calls


ALLOW_BODY = {
    "decision": "ALLOW",
    "trust_score": 0.91,
    "reasons": ["trust score 0.91 at or above 0.60"],
    "signals": {},
    "degraded_engines": [],
    "trace_id": "abc123",
    "audit_id": "f" * 64,
    "latency_ms": 3.2,
}
BLOCK_BODY = {**ALLOW_BODY, "decision": "BLOCK", "trust_score": 0.0, "reasons": ["policy veto"]}
REVIEW_BODY = {**ALLOW_BODY, "decision": "REVIEW", "trust_score": 0.45, "reasons": ["ambiguous"]}


class TestVerdict:
    def test_convenience_predicates(self):
        assert Verdict.from_response(ALLOW_BODY).allowed
        assert Verdict.from_response(BLOCK_BODY).blocked
        assert Verdict.from_response(REVIEW_BODY).needs_review

    def test_parses_the_full_response(self):
        verdict = Verdict.from_response(ALLOW_BODY)
        assert verdict.trust_score == pytest.approx(0.91)
        assert verdict.trace_id == "abc123"
        assert verdict.audit_id == "f" * 64
        assert not verdict.failed_open

    def test_missing_fields_default_to_a_permissive_verdict(self):
        """A truncated response must not crash the caller's request path."""
        verdict = Verdict.from_response({})
        assert verdict.decision == "ALLOW"
        assert verdict.trust_score == 1.0


class TestClientTransport:
    def test_sends_api_key_and_payload(self, monkeypatch):
        calls = fake_transport(monkeypatch, ALLOW_BODY)
        client = CustosClient("http://custos.test", "key-123")

        client.evaluate("m1", action="disburse", features={"x": 1.0}, context={"amount": 5})

        request = calls[0]["request"]
        assert request.get_header("X-api-key") == "key-123"
        assert request.full_url == "http://custos.test/v1/evaluate"
        body = json.loads(request.data)
        assert body == {
            "model_id": "m1",
            "action": "disburse",
            "features": {"x": 1.0},
            "context": {"amount": 5},
        }

    def test_timeout_is_passed_through_in_seconds(self, monkeypatch):
        calls = fake_transport(monkeypatch, ALLOW_BODY)
        CustosClient("http://custos.test", "k", timeout_ms=250).evaluate("m1")
        assert calls[0]["timeout"] == pytest.approx(0.25)

    def test_trailing_slash_in_base_url_is_normalised(self, monkeypatch):
        calls = fake_transport(monkeypatch, ALLOW_BODY)
        CustosClient("http://custos.test/", "k").evaluate("m1")
        assert calls[0]["request"].full_url == "http://custos.test/v1/evaluate"


class TestFailOpen:
    """ADR 0001 — a Custos outage must never become the caller's outage."""

    @pytest.mark.parametrize(
        "error",
        [
            TimeoutError("timed out"),
            urllib.error.URLError("connection refused"),
            ConnectionResetError("reset"),
            ValueError("garbage response"),
        ],
    )
    def test_any_transport_failure_yields_allow(self, monkeypatch, error):
        fake_transport(monkeypatch, raises=error)
        verdict = CustosClient("http://custos.test", "k").evaluate("m1")

        assert verdict.decision == "ALLOW"
        assert verdict.failed_open is True
        assert verdict.degraded_engines == ["*"]
        assert verdict.error

    def test_fail_open_verdict_is_distinguishable_from_a_real_allow(self, monkeypatch):
        """A caller needing strict enforcement checks failed_open, not decision."""
        fake_transport(monkeypatch, raises=TimeoutError())
        failed = CustosClient("http://custos.test", "k").evaluate("m1")

        fake_transport(monkeypatch, ALLOW_BODY)
        real = CustosClient("http://custos.test", "k").evaluate("m1")

        assert failed.allowed and real.allowed
        assert failed.failed_open and not real.failed_open

    def test_fail_closed_client_propagates_the_exception(self, monkeypatch):
        fake_transport(monkeypatch, raises=TimeoutError("timed out"))
        client = CustosClient("http://custos.test", "k", fail_open=False)
        with pytest.raises(TimeoutError):
            client.evaluate("m1")

    def test_fail_open_reason_explains_itself(self, monkeypatch):
        fake_transport(monkeypatch, raises=urllib.error.URLError("refused"))
        verdict = CustosClient("http://custos.test", "k").evaluate("m1")
        assert any("failed open" in r for r in verdict.reasons)


class TestEnforce:
    def test_allow_returns_the_verdict(self):
        verdict = Verdict.from_response(ALLOW_BODY)
        assert enforce(verdict) is verdict

    def test_block_raises(self):
        with pytest.raises(Blocked) as exc:
            enforce(Verdict.from_response(BLOCK_BODY))
        assert "policy veto" in str(exc.value)
        assert exc.value.verdict.decision == "BLOCK"

    def test_review_raises_rather_than_falling_through_to_allow(self):
        """A REVIEW that silently proceeds is indistinguishable from an ALLOW."""
        with pytest.raises(ReviewRequired):
            enforce(Verdict.from_response(REVIEW_BODY))

    def test_handlers_suppress_the_exceptions(self):
        seen = []
        enforce(Verdict.from_response(BLOCK_BODY), on_block=seen.append)
        enforce(Verdict.from_response(REVIEW_BODY), on_review=seen.append)
        assert [v.decision for v in seen] == ["BLOCK", "REVIEW"]

    def test_exception_message_carries_the_trace_id(self):
        with pytest.raises(Blocked) as exc:
            enforce(Verdict.from_response(BLOCK_BODY))
        assert "abc123" in str(exc.value)


class TestGuardDecorator:
    def test_allow_runs_the_wrapped_function(self, monkeypatch):
        fake_transport(monkeypatch, ALLOW_BODY)
        custos.configure("http://custos.test", "k")

        @custos.guard(model_id="m1", action="disburse")
        def disburse():
            return "money moved"

        assert disburse() == "money moved"

    def test_block_prevents_the_function_from_running(self, monkeypatch):
        fake_transport(monkeypatch, BLOCK_BODY)
        custos.configure("http://custos.test", "k")
        ran = []

        @custos.guard(model_id="m1")
        def disburse():
            ran.append(True)

        with pytest.raises(Blocked):
            disburse()
        assert ran == [], "the guarded body must not execute on BLOCK"

    def test_features_extracted_from_a_keyword_argument(self, monkeypatch):
        calls = fake_transport(monkeypatch, ALLOW_BODY)
        custos.configure("http://custos.test", "k")

        @custos.guard(model_id="m1", features="application", context="ctx")
        def score(*, application, ctx):
            return "ok"

        score(application={"income": 60000.0}, ctx={"amount": 5})

        body = json.loads(calls[0]["request"].data)
        assert body["features"] == {"income": 60000.0}
        assert body["context"] == {"amount": 5}

    def test_features_extracted_by_callable(self, monkeypatch):
        calls = fake_transport(monkeypatch, ALLOW_BODY)
        custos.configure("http://custos.test", "k")

        @custos.guard(model_id="m1", features=lambda app: {"income": app["income"]})
        def score(app):
            return "ok"

        score({"income": 42.0, "secret": "not sent"})
        assert json.loads(calls[0]["request"].data)["features"] == {"income": 42.0}

    def test_preserves_function_metadata(self, monkeypatch):
        fake_transport(monkeypatch, ALLOW_BODY)
        custos.configure("http://custos.test", "k")

        @custos.guard(model_id="m1", action="disburse")
        def disburse():
            """Original docstring."""

        assert disburse.__name__ == "disburse"
        assert disburse.__doc__ == "Original docstring."
        assert disburse.custos_model_id == "m1"

    def test_unconfigured_client_raises_a_clear_error(self):
        @custos.guard(model_id="m1")
        def disburse():
            return "money moved"

        with pytest.raises(RuntimeError, match="configure"):
            disburse()


class TestGateContextManager:
    def test_allow_enters_the_block(self, monkeypatch):
        fake_transport(monkeypatch, ALLOW_BODY)
        custos.configure("http://custos.test", "k")

        with custos.gate("m1", "disburse", features={"x": 1.0}) as verdict:
            assert verdict.allowed

    def test_block_never_enters_the_block(self, monkeypatch):
        fake_transport(monkeypatch, BLOCK_BODY)
        custos.configure("http://custos.test", "k")
        entered = []

        with pytest.raises(Blocked):
            with custos.gate("m1", "disburse"):
                entered.append(True)
        assert entered == []

    def test_review_handler_allows_the_block_to_run(self, monkeypatch):
        fake_transport(monkeypatch, REVIEW_BODY)
        custos.configure("http://custos.test", "k")
        held = []

        with custos.gate("m1", on_review=held.append) as verdict:
            assert verdict.needs_review
        assert len(held) == 1


class TestConfigure:
    def test_configure_returns_a_usable_client(self):
        client = custos.configure("http://custos.test/", "k", timeout_ms=99, fail_open=False)
        assert client is custos.get_client()
        assert client.base_url == "http://custos.test"
        assert client.timeout_ms == 99

    def test_get_client_before_configure_raises(self):
        with pytest.raises(RuntimeError):
            custos.get_client()
