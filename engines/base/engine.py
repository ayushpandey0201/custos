"""SignalEngine ABC — the ONE interface every engine obeys.

Rule: engines never import each other. Cross-engine flow goes through the Trust
Engine.

That rule is what makes a new signal a purely additive change: drop a folder
under ``engines/``, register it, and every tenant can enable it by name without
a line changing anywhere else. The moment one engine reads another's output
directly, that property is gone and the ordering becomes load-bearing.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from shared.schemas.evaluation import EvaluationContext
from shared.schemas.signals import SignalResult
from shared.telemetry import metrics


class SignalEngine(ABC):
    """Base class for every trust signal.

    Contract for implementors:

    * ``evaluate`` must not raise. Anything unexpected becomes a degraded
      result — one engine's bug must not take down the verdict (ADR 0001).
    * ``evaluate`` must be side-effect free with respect to ``ctx``: all engines
      share one context instance during fan-out.
    * ``evaluate`` must fit inside ``ENGINE_TIMEOUT_MS``. The Trust Engine
      enforces this by cancellation, so an engine that blocks the event loop
      cannot be timed out — do not do blocking I/O without a thread.
    """

    #: Registry name. Tenants enable engines by this string in their config.
    name: str = "base"

    @abstractmethod
    async def evaluate(self, ctx: EvaluationContext) -> SignalResult:
        """Return this engine's trust signal for one request."""
        ...

    async def evaluate_safely(self, ctx: EvaluationContext) -> SignalResult:
        """Run ``evaluate`` with timing and a failure firewall.

        The Trust Engine calls this, never ``evaluate`` directly.
        """
        started = time.perf_counter()
        try:
            result = await self.evaluate(ctx)
        except Exception as exc:
            result = SignalResult.degraded_result(
                self.name, reason="engine_error", error=f"{type(exc).__name__}: {exc}"
            )
        result.latency_ms = (time.perf_counter() - started) * 1000
        metrics.record_latency_ms(self.name, result.latency_ms)
        if result.degraded:
            metrics.record_degraded(self.name)
        if result.veto is not None:
            metrics.record_veto(self.name)
        return result
