"""Decision enum and DecisionRecord — the audited output of the Trust Engine."""

from enum import Enum

from pydantic import BaseModel


class Decision(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REVIEW = "REVIEW"


class DecisionRecord(BaseModel):
    decision: Decision
    trust_score: float
    tenant_id: str
    model_id: str

