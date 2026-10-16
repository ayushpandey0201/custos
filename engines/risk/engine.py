"""RiskEngine(SignalEngine): "How DANGEROUS is this particular request?"

Drift asks whether the *model* still fits its traffic. Policy asks whether an
action is *permitted*. Neither looks at whether this one request is unusual
for this tenant — and that is where a lot of real damage comes from: an amount
far outside anything the model normally approves, or one customer suddenly
firing requests in a burst. This engine answers that, from the request's
business ``context`` (never its model features, which are drift's job).

Two components, each optional:

  amount    How far ``context["amount"]`` sits above this tenant/model's
            recent amounts, as a *robust* z-score (median and MAD rather than
            mean and standard deviation, so the history it compares against
            cannot be dragged around by the very outliers it is looking for).

  velocity  How many requests the same subject (``customer_id``,
            ``account_id`` or ``subject_id`` in context) has made in the last
            minute. Bursts are a classic fraud and runaway-agent pattern.

Risk is the *worst* component, not the average: one red flag is enough, and
averaging would let a normal-looking velocity hide an extreme amount.

Refusing to guess, as everywhere else in Custos (ADR 0004):

* A component with no input, or an amount history too short to say what
  "normal" is, does not vote.
* If no component can vote, the engine returns *degraded* — excluded from
  fusion and recorded as such — never a confident "safe".

State is in-process and per tenant. That is right for a single gateway node;
across several workers each keeps its own view, which makes the signal slightly
less sensitive, never wrong. A shared Redis-backed history is the multi-node
step, and the seam for it is the two ``_History`` / ``_Velocity`` classes.
"""

from __future__ import annotations

import math
import time
from bisect import insort
from collections import OrderedDict, deque
from statistics import median

from engines.base.engine import SignalEngine
from shared.schemas.evaluation import EvaluationContext
from shared.schemas.signals import SignalResult

# --- amount ------------------------------------------------------------------
HISTORY_SIZE = 2000  # most recent amounts kept per (tenant, model)
MIN_HISTORY = 50  # below this, "normal" is not yet known; the component abstains
Z_SAFE = 3.0  # robust z at or below this carries no risk
Z_MAX = 10.0  # robust z at or above this is maximum risk
# A perfectly uniform history has MAD = 0, which would make *any* difference
# infinitely anomalous. Floor the spread at a fraction of the median instead.
SPREAD_FLOOR = 0.10

# --- velocity ----------------------------------------------------------------
WINDOW_S = 60.0
RATE_SAFE = 3  # requests per subject per window carrying no risk
RATE_MAX = 10  # requests per subject per window at maximum risk
MAX_SUBJECTS = 50_000  # bound on tracked subjects per process; oldest evicted

SUBJECT_KEYS = ("customer_id", "account_id", "subject_id")


def _ramp(value: float, safe: float, worst: float) -> float:
    """0 at or below ``safe``, 1 at or above ``worst``, linear between."""
    if value <= safe:
        return 0.0
    if value >= worst:
        return 1.0
    return (value - safe) / (worst - safe)


class _History:
    """Recent amounts for one (tenant, model), with a sorted copy for medians."""

    def __init__(self) -> None:
        self.recent: deque[float] = deque()
        self.ordered: list[float] = []

    def add(self, value: float) -> None:
        if len(self.recent) == HISTORY_SIZE:
            self.ordered.remove(self.recent.popleft())
        self.recent.append(value)
        insort(self.ordered, value)

    def robust_z(self, value: float) -> tuple[float, float] | None:
        """(z, median), or None while the history is too short to judge."""
        if len(self.ordered) < MIN_HISTORY:
            return None
        mid = median(self.ordered)
        mad = median(abs(v - mid) for v in self.ordered)
        # 1.4826 makes MAD comparable to a standard deviation for normal data.
        scale = max(1.4826 * mad, SPREAD_FLOOR * abs(mid), 1e-9)
        return (value - mid) / scale, mid


class _Velocity:
    """Request timestamps per (tenant, subject), bounded in both directions."""

    def __init__(self) -> None:
        self.seen: OrderedDict[tuple[str, str], deque[float]] = OrderedDict()

    def hit(self, key: tuple[str, str], now: float) -> int:
        """Record a request and return how many fall inside the window."""
        stamps = self.seen.pop(key, None) or deque()
        stamps.append(now)
        while stamps and stamps[0] < now - WINDOW_S:
            stamps.popleft()
        self.seen[key] = stamps  # re-insert as most recently used
        while len(self.seen) > MAX_SUBJECTS:
            self.seen.popitem(last=False)
        return len(stamps)


_amounts: dict[tuple[str, str], _History] = {}
_velocity = _Velocity()


def reset_state() -> None:
    """Forget all history. Tests use this; nothing on the hot path does."""
    _amounts.clear()
    _velocity.seen.clear()


def _subject(ctx: EvaluationContext) -> str | None:
    for key in SUBJECT_KEYS:
        value = ctx.context.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _amount(ctx: EvaluationContext) -> float | None:
    try:
        value = float(ctx.context.get("amount"))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


class RiskEngine(SignalEngine):
    """Trust = 1 − the worst risk component that had enough information to vote."""

    name = "risk"

    async def evaluate(self, ctx: EvaluationContext) -> SignalResult:
        # No awaits below: the read-score-record sequence runs atomically on the
        # event loop, so concurrent requests cannot interleave inside it.
        components: dict[str, dict] = {}
        abstained: dict[str, str] = {}

        amount = _amount(ctx)
        if amount is None:
            abstained["amount"] = "no amount in context"
        else:
            history = _amounts.setdefault((ctx.tenant_id, ctx.model_id), _History())
            judged = history.robust_z(amount)
            if judged is None:
                seen = len(history.ordered)
                abstained["amount"] = f"warming up: {seen}/{MIN_HISTORY} amounts seen"
            else:
                z, mid = judged
                components["amount"] = {
                    "value": round(amount, 2),
                    "typical": round(mid, 2),
                    "robust_z": round(z, 2),
                    "risk": round(_ramp(z, Z_SAFE, Z_MAX), 4),
                }
            # Recorded after scoring, so a request is judged against what came
            # before it rather than partly against itself.
            history.add(amount)

        subject = _subject(ctx)
        if subject is None:
            abstained["velocity"] = "no customer_id/account_id/subject_id in context"
        else:
            count = _velocity.hit((ctx.tenant_id, subject), time.monotonic())
            components["velocity"] = {
                "requests_last_minute": count,
                "risk": round(_ramp(count, RATE_SAFE, RATE_MAX), 4),
            }

        if not components:
            return SignalResult.degraded_result(
                self.name, reason="insufficient_context", abstained=abstained
            )

        worst_name, worst = max(components.items(), key=lambda kv: kv[1]["risk"])
        risk = worst["risk"]
        return SignalResult(
            engine=self.name,
            score=max(0.0, min(1.0, 1.0 - risk)),
            degraded=False,
            detail={
                "risk": round(risk, 4),
                "driven_by": worst_name if risk > 0 else None,
                "components": components,
                "abstained": abstained,
            },
        )
