"""EvaluationRequest, EvaluationContext, EvaluationResponse — wire + internal contracts.

``EvaluationRequest`` is what a caller PUTs on the wire. ``EvaluationContext``
is the enriched, tenant-resolved form the Trust Engine and every engine sees.
``EvaluationResponse`` is what goes back, and — minus the timing fields — what
gets written to the audit chain.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from shared.schemas.decision import Decision
from shared.schemas.signals import SignalResult


def _trace_id() -> str:
    return uuid.uuid4().hex


class EvaluationRequest(BaseModel):
    """The wire contract. Deliberately small — the SDK must stay a 5-line integration."""

    model_id: str = Field(description="Model the caller is about to act on the output of")
    action: str = Field(default="predict", description="What the caller wants to do")
    features: dict[str, float] = Field(
        default_factory=dict,
        description="Feature vector the model scored; used for drift attribution",
    )
    context: dict = Field(
        default_factory=dict,
        description="Business facts the policy engine matches rules against",
    )
    trace_id: str = Field(default_factory=_trace_id)


class EvaluationContext(BaseModel):
    """Request + resolved tenant identity. This is what engines receive.

    Engines get a read-only view: they may inspect anything here but must not
    mutate it, since all engines see the same instance during fan-out.
    """

    tenant_id: str
    model_id: str
    action: str = "predict"
    features: dict[str, float] = Field(default_factory=dict)
    context: dict = Field(default_factory=dict)
    trace_id: str = Field(default_factory=_trace_id)
    model_known: bool = Field(
        default=True,
        description="False when model_id was never registered; forces REVIEW per ADR 0005",
    )

    @classmethod
    def from_request(
        cls, request: EvaluationRequest, tenant_id: str, model_known: bool = True
    ) -> EvaluationContext:
        return cls(
            tenant_id=tenant_id,
            model_id=request.model_id,
            action=request.action,
            features=request.features,
            context=request.context,
            trace_id=request.trace_id,
            model_known=model_known,
        )


class EvaluationResponse(BaseModel):
    """The verdict returned to the caller and recorded in the audit chain."""

    decision: Decision
    trust_score: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(
        default_factory=list, description="Human-readable justification, ordered by weight"
    )
    signals: dict[str, SignalResult] = Field(default_factory=dict)
    degraded_engines: list[str] = Field(default_factory=list)
    trace_id: str = ""
    audit_id: str | None = Field(default=None, description="Hash of this decision's audit entry")
    latency_ms: float = 0.0
