"""RuntimeTrustScore: weighted fusion of signals + veto handling."""

from shared.schemas.signals import SignalResult


def aggregate(signals: list[SignalResult], weights: dict[str, float]) -> float:
    raise NotImplementedError

