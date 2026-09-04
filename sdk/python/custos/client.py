"""Thin HTTP client: timeout handling + fail-open logic.

See docs/adr/0001-fail-open-default.md.

Built on ``urllib`` from the standard library rather than ``requests`` or
``httpx``. This client is imported into someone else's production service, and
every dependency it carries is a dependency it can force them to resolve a
version conflict over. The HTTP surface here is one POST — it does not justify
that cost.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

DEFAULT_TIMEOUT_MS = 50


@dataclass
class Verdict:
    """What the caller gets back, whether or not Custos actually answered."""

    decision: str
    trust_score: float
    reasons: list[str] = field(default_factory=list)
    signals: dict = field(default_factory=dict)
    degraded_engines: list[str] = field(default_factory=list)
    trace_id: str = ""
    audit_id: str | None = None
    latency_ms: float = 0.0
    #: True when Custos did not answer and the SDK synthesised an ALLOW.
    #: Callers that need strict enforcement check this, not ``decision``.
    failed_open: bool = False
    error: str | None = None

    @property
    def allowed(self) -> bool:
        return self.decision == "ALLOW"

    @property
    def blocked(self) -> bool:
        return self.decision == "BLOCK"

    @property
    def needs_review(self) -> bool:
        return self.decision == "REVIEW"

    @classmethod
    def from_response(cls, data: dict) -> Verdict:
        return cls(
            decision=data.get("decision", "ALLOW"),
            trust_score=float(data.get("trust_score", 1.0)),
            reasons=data.get("reasons", []),
            signals=data.get("signals", {}),
            degraded_engines=data.get("degraded_engines", []),
            trace_id=data.get("trace_id", ""),
            audit_id=data.get("audit_id"),
            latency_ms=float(data.get("latency_ms", 0.0)),
        )

    @classmethod
    def fail_open(cls, error: str) -> Verdict:
        return cls(
            decision="ALLOW",
            trust_score=1.0,
            reasons=[f"custos unreachable, failed open: {error}"],
            degraded_engines=["*"],
            failed_open=True,
            error=error,
        )


class CustosClient:
    """Client for the Custos gateway.

    Args:
        fail_open: when True (default, per ADR 0001) any transport failure or
            timeout yields an ALLOW verdict with ``failed_open=True``. When
            False the underlying exception propagates, which is what a tenant
            with a hard compliance requirement wants.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        fail_open: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_ms = timeout_ms
        self._fail_open = fail_open

    def evaluate(
        self,
        model_id: str,
        action: str = "predict",
        features: dict[str, float] | None = None,
        context: dict[str, Any] | None = None,
    ) -> Verdict:
        """Ask Custos whether to proceed. Never raises when ``fail_open``."""
        payload = {
            "model_id": model_id,
            "action": action,
            "features": features or {},
            "context": context or {},
        }
        started = time.perf_counter()

        try:
            data = self._post("/v1/evaluate", payload)
            return Verdict.from_response(data)
        except Exception as exc:
            if not self._fail_open:
                raise
            elapsed_ms = (time.perf_counter() - started) * 1000
            verdict = Verdict.fail_open(f"{type(exc).__name__}: {exc}")
            verdict.latency_ms = round(elapsed_ms, 3)
            return verdict

    def _post(self, path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            url=f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-API-Key": self.api_key},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_ms / 1000) as response:
            return json.loads(response.read().decode("utf-8"))

    def health(self) -> dict:
        with urllib.request.urlopen(f"{self.base_url}/health", timeout=2.0) as response:
            return json.loads(response.read().decode("utf-8"))
