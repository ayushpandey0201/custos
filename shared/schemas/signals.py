"""SignalResult, VetoInfo — the contract every engine returns through."""

from pydantic import BaseModel


class VetoInfo(BaseModel):
    engine: str
    reason: str


class SignalResult(BaseModel):
    engine: str
    score: float
    degraded: bool = False
    veto: VetoInfo | None = None

