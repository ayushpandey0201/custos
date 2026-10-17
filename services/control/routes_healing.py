"""Governed self-healing: the incident queue and the human decisions on it.

    POST /healing/scan/{model_id}                 detect + diagnose now
    GET  /healing/incidents                        the queue (?status=open)
    GET  /healing/incidents/{id}
    POST /healing/incidents/{id}/verify            did the applied repair work?
    POST /healing/incidents/{id}/close             a person closes it without a repair
    POST /healing/remediations/{id}/approve        a person authorises a repair; it is applied
    POST /healing/remediations/{id}/reject
    POST /healing/remediations/{id}/retest         re-run the shadow test on current traffic

Approve, reject and close require ``approver`` — a name, recorded on the audit
chain with the decision. Custos has tenant API keys, not user accounts, so the
name is attested by whoever holds the key rather than verified; the chain makes
it impossible to change afterwards, not impossible to misstate at the time.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services.gateway.auth import require_tenant
from services.healing import service

router = APIRouter(prefix="/healing", tags=["healing"])


class HumanDecision(BaseModel):
    approver: str = Field(min_length=1, max_length=128)
    note: str = Field(default="", max_length=2000)


def _call(fn, *args):
    try:
        return fn(*args)
    except service.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except service.Conflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/scan/{model_id}")
def scan(model_id: str, tenant_id: str = Depends(require_tenant)) -> dict:
    return _call(service.scan, tenant_id, model_id)


@router.get("/incidents")
def incidents(
    status: str | None = Query(default=None, pattern="^(open|resolved)$"),
    model_id: str | None = None,
    limit: int = Query(default=50, le=200),
    tenant_id: str = Depends(require_tenant),
) -> list[dict]:
    return service.list_incidents(tenant_id, status=status, model_id=model_id, limit=limit)


@router.get("/incidents/{incident_id}")
def incident(incident_id: int, tenant_id: str = Depends(require_tenant)) -> dict:
    return _call(service.get_incident, tenant_id, incident_id)


@router.post("/incidents/{incident_id}/verify")
def verify(incident_id: int, tenant_id: str = Depends(require_tenant)) -> dict:
    return _call(service.verify, tenant_id, incident_id)


@router.post("/incidents/{incident_id}/close")
def close(incident_id: int, body: HumanDecision, tenant_id: str = Depends(require_tenant)) -> dict:
    return _call(service.close, tenant_id, incident_id, body.approver, body.note)


@router.post("/remediations/{remediation_id}/approve")
def approve(
    remediation_id: int, body: HumanDecision, tenant_id: str = Depends(require_tenant)
) -> dict:
    return _call(service.approve, tenant_id, remediation_id, body.approver, body.note)


@router.post("/remediations/{remediation_id}/reject")
def reject(
    remediation_id: int, body: HumanDecision, tenant_id: str = Depends(require_tenant)
) -> dict:
    return _call(service.reject, tenant_id, remediation_id, body.approver, body.note)


@router.post("/remediations/{remediation_id}/retest")
def retest(remediation_id: int, tenant_id: str = Depends(require_tenant)) -> dict:
    return _call(service.retest, tenant_id, remediation_id)
