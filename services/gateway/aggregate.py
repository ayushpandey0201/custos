"""RuntimeTrustScore: weighted fusion of signals + veto handling.

Turns N independent engine opinions into one number. Three rules, in order:

  1. Degraded signals are *excluded*, not defaulted. An engine with no answer
     must not contribute a free 1.0 (ADR 0004).
  2. Surviving weights are renormalised, so removing an engine reweights the
     rest rather than silently dragging the score toward zero.
  3. A veto sets a ceiling of 0.0 that no amount of weighted agreement can lift.

Fusion is a weighted mean rather than a product or a min. A product punishes
every additional engine you enable, and a min discards all evidence but one —
both make adding a signal to the system feel expensive, which is the opposite
of what the engine seam is for.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shared.schemas.signals import SignalResult, VetoInfo

# Trust score once any engine has vetoed. Not a tunable: a veto means "do not
# proceed", and a configurable veto would make it a suggestion.
VETO_CEILING = 0.0


@dataclass
class AggregateResult:
    """The fused score plus everything needed to explain it in an audit record."""

    score: float
    vetoes: list[VetoInfo] = field(default_factory=list)
    degraded_engines: list[str] = field(default_factory=list)
    contributions: dict[str, float] = field(default_factory=dict)
    all_degraded: bool = False

    @property
    def vetoed(self) -> bool:
        return bool(self.vetoes)


def aggregate(signals: list[SignalResult], weights: dict[str, float]) -> AggregateResult:
    """Fuse engine signals into a single trust score in [0, 1].

    Args:
        signals: one result per enabled engine.
        weights: engine name -> relative weight. Engines missing from this map
            contribute nothing; an engine that is running but unweighted is a
            configuration mistake, and scoring it as 0 weight makes that
            visible in ``contributions`` rather than guessing a default.
    """
    vetoes = [s.veto for s in signals if s.veto is not None]
    degraded = [s.engine for s in signals if s.degraded]

    active = [s for s in signals if not s.degraded and weights.get(s.engine, 0.0) > 0]
    total_weight = sum(weights.get(s.engine, 0.0) for s in active)

    if not active or total_weight <= 0:
        # Nothing to fuse. The score is meaningless here; ``all_degraded`` is
        # the load-bearing field and the decision layer routes on it.
        return AggregateResult(
            score=VETO_CEILING if vetoes else 1.0,
            vetoes=vetoes,
            degraded_engines=degraded,
            contributions={},
            all_degraded=True,
        )

    contributions = {s.engine: weights[s.engine] / total_weight for s in active}
    score = sum(s.score * contributions[s.engine] for s in active)

    if vetoes:
        score = min(score, VETO_CEILING)

    return AggregateResult(
        score=max(0.0, min(1.0, score)),
        vetoes=vetoes,
        degraded_engines=degraded,
        contributions={k: round(v, 4) for k, v in contributions.items()},
        all_degraded=False,
    )
