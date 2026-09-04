"""Decision enum and DecisionRecord — the audited output of the Trust Engine."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


class Decision(str, Enum):
    """The only three answers Custos ever gives.

    ALLOW  — proceed.
    REVIEW — proceed only through a human/secondary path; the caller decides how.
    BLOCK  — do not proceed.
    """

    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REVIEW = "REVIEW"


class DecisionRecord(BaseModel):
    """A decision, frozen for the audit chain.

    This is the payload that gets hashed. Field order is irrelevant (the audit
    layer canonicalises before hashing) but the *content* is load-bearing: an
    auditor must be able to reconstruct why the decision was made from this
    record alone, without replaying the request.
    """

    decision: Decision
    trust_score: float
    tenant_id: str
    model_id: str
    action: str = "predict"
    trace_id: str = ""
    reasons: list[str] = Field(default_factory=list)
    signals: dict = Field(default_factory=dict)
    degraded_engines: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
