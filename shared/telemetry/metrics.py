"""Counters + histograms: decisions, latencies, degradations.

An in-process registry with a Prometheus text exposition endpoint. Deliberately
not a Prometheus client dependency: the metric set is small and fixed, and the
exposition format is a dozen lines to emit.

The three things worth alerting on are all here — how often we block, how often
an engine gives up (degraded), and where the hot path spends its latency budget.
"""

from __future__ import annotations

import math
import threading
from collections import defaultdict

_lock = threading.Lock()
_counters: dict[tuple[str, tuple[tuple[str, str], ...]], int] = defaultdict(int)
_latencies: dict[str, list[float]] = defaultdict(list)

# Ring size per series. Percentiles over the last N samples are what you want
# operationally, and it bounds memory without a time-series database.
_MAX_SAMPLES = 1000


def _key(name: str, labels: dict[str, str] | None):
    return (name, tuple(sorted((labels or {}).items())))


def increment(name: str, labels: dict[str, str] | None = None, by: int = 1) -> None:
    with _lock:
        _counters[_key(name, labels)] += by


def record_decision(decision: str, tenant_id: str = "unknown") -> None:
    increment("custos_decisions_total", {"decision": decision, "tenant": tenant_id})


def record_degraded(engine: str) -> None:
    increment("custos_engine_degraded_total", {"engine": engine})


def record_veto(engine: str) -> None:
    increment("custos_engine_veto_total", {"engine": engine})


def record_latency_ms(engine: str, ms: float) -> None:
    with _lock:
        samples = _latencies[engine]
        samples.append(ms)
        if len(samples) > _MAX_SAMPLES:
            del samples[0]


def percentile(engine: str, p: float) -> float:
    """Nearest-rank percentile over the retained window. 0.0 when no samples.

    Rank is ``ceil(p/100 · n)``, the standard nearest-rank definition. Built on
    ``ceil`` rather than ``round`` deliberately: Python's ``round`` is
    banker's rounding, so a half-way rank alternates between neighbours
    depending on parity — which makes a latency percentile quietly report the
    wrong sample for some window sizes and not others.
    """
    with _lock:
        samples = sorted(_latencies.get(engine, []))
    if not samples:
        return 0.0
    rank = math.ceil(max(0.0, min(100.0, p)) / 100.0 * len(samples))
    return samples[min(len(samples) - 1, max(rank - 1, 0))]


def snapshot() -> dict:
    """Everything, as plain data. Used by tests and the /metrics JSON view."""
    with _lock:
        counters = {
            (
                name + ("{" + ",".join(f'{k}="{v}"' for k, v in labels) + "}" if labels else "")
            ): count
            for (name, labels), count in _counters.items()
        }
        engines = list(_latencies)
    return {
        "counters": counters,
        "latency_ms": {
            engine: {
                "p50": percentile(engine, 50),
                "p95": percentile(engine, 95),
                "p99": percentile(engine, 99),
                "count": len(_latencies[engine]),
            }
            for engine in engines
        },
    }


def render_prometheus() -> str:
    """Prometheus text exposition format."""
    data = snapshot()
    lines: list[str] = []
    for series, value in sorted(data["counters"].items()):
        lines.append(f"{series} {value}")
    for engine, stats in sorted(data["latency_ms"].items()):
        for quantile, key in (("0.5", "p50"), ("0.95", "p95"), ("0.99", "p99")):
            lines.append(
                f'custos_latency_ms{{engine="{engine}",quantile="{quantile}"}} {stats[key]:.3f}'
            )
        lines.append(f'custos_latency_count{{engine="{engine}"}} {stats["count"]}')
    return "\n".join(lines) + "\n"


def reset() -> None:
    with _lock:
        _counters.clear()
        _latencies.clear()
