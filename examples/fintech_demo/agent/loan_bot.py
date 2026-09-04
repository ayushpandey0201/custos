"""Fake auto-decisioner: scores -> calls @guard -> approve/deny.

This is the integration Custos is selling. The whole trust layer costs this
agent four lines: one import, one configure, one decorator, one exception
handler. Everything else in this file is the lending logic that would exist
anyway.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "sdk" / "python"))

import custos  # noqa: E402
from custos import Blocked, ReviewRequired  # noqa: E402

from examples.fintech_demo.model.train import (  # noqa: E402
    load,
    predict_default_probability,
)

MODEL_ID = "credit-risk-v3"
APPROVAL_THRESHOLD = 0.35


@dataclass
class Outcome:
    """What the bot did, and why."""

    verdict: str  # APPROVED | DENIED | HELD_FOR_REVIEW | BLOCKED
    default_probability: float
    reason: str
    trust_score: float | None = None
    trace_id: str = ""


class LoanBot:
    """Auto-decisions loan applications, gated by Custos."""

    def __init__(self, gateway_url: str, api_key: str) -> None:
        # (1) Point the SDK at the gateway.
        custos.configure(base_url=gateway_url, api_key=api_key, timeout_ms=200)
        self._model = load()
        self.held: list[Outcome] = []

    def decide(self, application: dict[str, float], amount: float) -> Outcome:
        """Score an application and act on it — if Custos permits.

        The model produces a number regardless. Custos decides whether that
        number is currently trustworthy enough to act on automatically, which
        is the distinction this whole project exists to make: a model that is
        *running* is not the same as a model that is *reliable*.
        """
        probability = predict_default_probability(self._model, application)

        try:
            # (2) Gate the consequential action, not the scoring.
            with custos.gate(
                model_id=MODEL_ID,
                action="disburse",
                features=application,
                context={"amount": amount, "region": "IN"},
            ) as verdict:
                if probability <= APPROVAL_THRESHOLD:
                    return Outcome(
                        "APPROVED",
                        probability,
                        f"default risk {probability:.1%} within appetite",
                        verdict.trust_score,
                        verdict.trace_id,
                    )
                return Outcome(
                    "DENIED",
                    probability,
                    f"default risk {probability:.1%} above appetite",
                    verdict.trust_score,
                    verdict.trace_id,
                )

        except ReviewRequired as exc:
            # (3) REVIEW means a human decides. The model's score is retained
            # as an input to that decision, not discarded.
            outcome = Outcome(
                "HELD_FOR_REVIEW",
                probability,
                "; ".join(exc.verdict.reasons),
                exc.verdict.trust_score,
                exc.verdict.trace_id,
            )
            self.held.append(outcome)
            return outcome

        except Blocked as exc:
            # (4) BLOCK means do not act, at all.
            return Outcome(
                "BLOCKED",
                probability,
                "; ".join(exc.verdict.reasons),
                exc.verdict.trust_score,
                exc.verdict.trace_id,
            )


# The decorator form, for callers whose whole function is the guarded action.
@custos.guard(
    model_id=MODEL_ID,
    action="disburse",
    features="application",
    context="context",
)
def disburse(*, application: dict[str, float], context: dict) -> str:
    """Only runs if Custos returns ALLOW; otherwise raises before any money moves."""
    return f"disbursed {context['amount']:.0f} to applicant"
