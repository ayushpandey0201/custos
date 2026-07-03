"""Counters + histograms: decisions, latencies, degradations."""


def record_decision(decision: str) -> None:
    raise NotImplementedError


def record_latency_ms(engine: str, ms: float) -> None:
    raise NotImplementedError

