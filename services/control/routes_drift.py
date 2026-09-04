"""GET /models/{id}/drift — history for dashboard."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from engines.drift.severity import severity_band, top_contributors
from services.gateway.auth import require_tenant
from shared.db.models import DriftSnapshot
from shared.db.session import get_db
from shared.timeutil import iso_utc

# Shares the /models prefix with routes_models: drift history is a property of
# a model, so it belongs under the model's own resource path.
router = APIRouter(prefix="/models", tags=["drift"])


@router.get("/{model_id}/drift")
def drift_history(
    model_id: str,
    limit: int = Query(default=30, le=200),
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_db),
) -> dict:
    """Severity over time plus the current per-feature breakdown.

    The breakdown is the actionable part: severity says *that* the model has
    moved, the per-feature view says *which* input moved — which is what
    decides whether this is a population shift or a broken pipeline.
    """
    rows = list(
        db.execute(
            select(DriftSnapshot)
            .where(DriftSnapshot.tenant_id == tenant_id, DriftSnapshot.model_id == model_id)
            .order_by(DriftSnapshot.computed_at.desc(), DriftSnapshot.id.desc())
            .limit(limit)
        ).scalars()
    )

    if not rows:
        return {
            "model_id": model_id,
            "current": None,
            "history": [],
            "detail": "no drift snapshots computed yet",
        }

    latest = rows[0]
    history = [
        {
            "severity": round(r.severity, 4),
            "band": severity_band(r.severity),
            "sample_size": r.sample_size,
            "computed_at": iso_utc(r.computed_at),
        }
        # Reverse so the dashboard receives oldest-first, ready to plot.
        for r in reversed(rows)
    ]

    return {
        "model_id": model_id,
        "current": {
            "severity": round(latest.severity, 4),
            "band": severity_band(latest.severity),
            "sample_size": latest.sample_size,
            "computed_at": iso_utc(latest.computed_at),
            "per_feature": {
                name: {
                    "psi": round(stats.get("psi", 0.0), 4),
                    "ks": round(stats.get("ks", 0.0), 4),
                    "severity": round(stats.get("severity", 0.0), 4),
                    "band": severity_band(stats.get("severity", 0.0)),
                }
                for name, stats in (latest.per_feature or {}).items()
            },
            "top_features": [
                {"feature": name, "severity": round(value, 4)}
                for name, value in top_contributors(latest.per_feature or {}, limit=5)
            ],
        },
        "history": history,
    }
