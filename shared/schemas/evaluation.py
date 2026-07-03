"""EvaluationRequest, EvaluationContext, EvaluationResponse — wire + internal contracts."""

from pydantic import BaseModel


class EvaluationContext(BaseModel):
    tenant_id: str
    model_id: str


class EvaluationRequest(BaseModel):
    context: EvaluationContext
    payload: dict


class EvaluationResponse(BaseModel):
    decision: str
    trust_score: float
    signals: dict

