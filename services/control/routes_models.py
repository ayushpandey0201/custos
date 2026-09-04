"""POST /models, POST /models/{id}/baseline, GET /models."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from engines.drift import worker
from services.gateway.auth import require_tenant
from shared.db.models import FeatureSample, Model
from shared.db.registry import invalidate_model_registration
from shared.db.session import get_db
from shared.timeutil import iso_utc

router = APIRouter(prefix="/models", tags=["models"])


class RegisterModelRequest(BaseModel):
    model_id: str
    name: str = ""
    version: str = "1"


class BaselineRequest(BaseModel):
    """Reference sample for a model.

    Supplied as rows rather than pre-aggregated statistics so Custos can
    recompute PSI with different bucketing later without asking for the data
    again — the bucket count is our implementation detail, not the tenant's.
    """

    samples: list[dict[str, float]] = Field(min_length=1)


class ModelOut(BaseModel):
    model_id: str
    name: str
    version: str
    status: str
    has_baseline: bool
    baseline_features: int
    baseline_at: str | None
    registered_at: str


def _to_out(model: Model) -> ModelOut:
    return ModelOut(
        model_id=model.model_id,
        name=model.name,
        version=model.version,
        status=model.status,
        has_baseline=bool(model.baseline),
        baseline_features=len(model.baseline or {}),
        baseline_at=iso_utc(model.baseline_at),
        registered_at=iso_utc(model.registered_at) or "",
    )


@router.post("", response_model=ModelOut, status_code=201)
def register_model(
    body: RegisterModelRequest,
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_db),
) -> ModelOut:
    """Register a model so its traffic stops routing to REVIEW (ADR 0005)."""
    existing = db.execute(
        select(Model).where(Model.tenant_id == tenant_id, Model.model_id == body.model_id)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"model {body.model_id!r} already registered")

    model = Model(tenant_id=tenant_id, model_id=body.model_id, name=body.name, version=body.version)
    db.add(model)
    db.flush()

    # The gateway caches the negative result of this lookup. Evict it, or a
    # model registered a second ago keeps routing to REVIEW.
    invalidate_model_registration(tenant_id, body.model_id)
    return _to_out(model)


@router.get("", response_model=list[ModelOut])
def list_models(
    tenant_id: str = Depends(require_tenant), db: Session = Depends(get_db)
) -> list[ModelOut]:
    rows = db.execute(
        select(Model).where(Model.tenant_id == tenant_id).order_by(Model.registered_at.desc())
    ).scalars()
    return [_to_out(m) for m in rows]


@router.post("/{model_id}/baseline", status_code=201)
def set_baseline(
    model_id: str,
    body: BaselineRequest,
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_db),
) -> dict:
    """Capture the reference distribution drift will be measured against.

    Rows are stored as feature samples as well as folded into the baseline, so
    the same data is available if the baseline is ever rebuilt.
    """
    model = db.execute(
        select(Model).where(Model.tenant_id == tenant_id, Model.model_id == model_id)
    ).scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail=f"model {model_id!r} not registered")

    for row in body.samples:
        db.add(FeatureSample(tenant_id=tenant_id, model_id=model_id, features=row))
    db.commit()

    baseline = worker.build_baseline(tenant_id, model_id, samples=body.samples)
    return {
        "model_id": model_id,
        "features": sorted(baseline),
        "sample_size": len(body.samples),
    }


@router.post("/{model_id}/recompute", status_code=200)
def recompute(
    model_id: str,
    window_hours: int = 24,
    tenant_id: str = Depends(require_tenant),
) -> dict:
    """Trigger a drift recompute now instead of waiting for the schedule.

    Synchronous on purpose. This is an operator action on the cold control
    plane — an operator who asks for a recompute wants the number, not a task
    id. The scheduled path stays asynchronous via Celery.
    """
    result = worker.recompute_drift(tenant_id, model_id, window_hours=window_hours)
    if result is None:
        return {
            "model_id": model_id,
            "computed": False,
            "detail": "no baseline, or too few samples in the window",
        }
    return {
        "model_id": model_id,
        "computed": True,
        "severity": round(result["severity"], 4),
        "sample_size": result["sample_size"],
    }
