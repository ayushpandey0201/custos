"""SignalResult, VetoInfo — the contract every engine returns through.

A signal is always expressed as *trust*, not risk: ``score`` is 1.0 when the
engine is fully confident the request is safe and 0.0 when it is certain it is
not. Every engine, present and future, speaks this one dialect so the Trust
Engine can fuse them without knowing what any of them mean.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class VetoInfo(BaseModel):
    """A hard stop raised by a single engine.

    A veto bypasses weighted fusion entirely: no combination of other high
    signals can outvote it. Reserved for statements an engine can make with
    certainty ("this action is forbidden by policy"), never for statements of
    degree ("this looks risky").
    """

    engine: str
    reason: str
    rule_id: str | None = None


class SignalResult(BaseModel):
    """One engine's verdict on one request."""

    engine: str
    score: float = Field(ge=0.0, le=1.0, description="Trust in [0,1]; 1.0 = fully trusted")
    degraded: bool = Field(
        default=False,
        description="Engine could not reach a confident answer; excluded from fusion",
    )
    veto: VetoInfo | None = None
    latency_ms: float = 0.0
    detail: dict = Field(default_factory=dict, description="Engine-specific evidence for audit")

    @classmethod
    def degraded_result(cls, engine: str, reason: str, **detail) -> SignalResult:
        """Build the canonical 'I have no confident signal' result.

        Used whenever an engine is missing its inputs. Per ADR 0004 this is a
        distinct state from a confident 1.0 — it is visible in aggregation and
        recorded in the audit trail rather than silently reading as 'safe'.
        """
        return cls(
            engine=engine,
            score=1.0,
            degraded=True,
            detail={"reason": reason, **detail},
        )
