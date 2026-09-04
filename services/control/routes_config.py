"""PUT /config — tenant engines, weights, thresholds."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from engines import registry
from engines.policy import engine as policy_engine
from engines.policy.rules import Rule, RuleSyntaxError
from services.gateway.auth import require_tenant
from shared.config.tenant import TenantConfig, invalidate_tenant_config, load_tenant_config
from shared.db.models import PolicyRule, Tenant
from shared.db.session import get_db

router = APIRouter(prefix="/config", tags=["config"])


class ConfigUpdate(BaseModel):
    enabled_engines: list[str] | None = None
    weights: dict[str, float] | None = None
    thresholds: dict[str, float] | None = None
    fail_open: bool | None = None


class RuleUpsert(BaseModel):
    rule_id: str
    condition: str
    action: str = "veto"
    description: str = ""
    enabled: bool = True


@router.get("", response_model=TenantConfig)
def get_config(tenant_id: str = Depends(require_tenant)) -> TenantConfig:
    return load_tenant_config(tenant_id)


@router.put("", response_model=TenantConfig)
def update_config(
    body: ConfigUpdate,
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_db),
) -> TenantConfig:
    """Patch a tenant's config. Only supplied fields change.

    Validation happens here, on the cold path, so an incoherent config can
    never reach the hot one.
    """
    current = load_tenant_config(tenant_id)
    merged = current.model_dump()
    merged.update({k: v for k, v in body.model_dump().items() if v is not None})

    if body.enabled_engines is not None:
        registry.load_builtin_engines()
        unknown = sorted(set(body.enabled_engines) - set(registry.REGISTRY))
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"unknown engines {unknown}; registered: {sorted(registry.REGISTRY)}",
            )

    try:
        config = TenantConfig(**merged)
    except ValidationError as exc:
        # include_context=False drops the raw exception objects Pydantic
        # attaches to custom-validator errors. They are not JSON-serialisable,
        # so returning them turns a tenant's bad input into a 500 on our side.
        raise HTTPException(
            status_code=400,
            detail=exc.errors(include_context=False, include_url=False, include_input=False),
        ) from exc

    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id!r} not found")

    stored = config.model_dump()
    stored.pop("tenant_id")
    tenant.config = stored
    db.commit()

    # The gateway caches config for TENANT_CONFIG_TTL_S; evict so the change is
    # live immediately rather than at the end of an arbitrary TTL.
    invalidate_tenant_config(tenant_id)
    return config


@router.get("/rules")
def list_rules(
    tenant_id: str = Depends(require_tenant), db: Session = Depends(get_db)
) -> list[dict]:
    from sqlalchemy import select

    rows = db.execute(select(PolicyRule).where(PolicyRule.tenant_id == tenant_id)).scalars()
    return [
        {
            "rule_id": r.rule_id,
            "condition": r.condition,
            "action": r.action,
            "description": r.description,
            "enabled": r.enabled,
        }
        for r in rows
    ]


@router.put("/rules")
def upsert_rule(
    body: RuleUpsert,
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_db),
) -> dict:
    """Create or replace a policy rule.

    The condition is parsed here and rejected if malformed. A rule that cannot
    be parsed must never be stored: the policy engine skips unparseable rules
    on the hot path, so a bad rule saved silently would be a policy that
    quietly does not apply.
    """
    from sqlalchemy import select

    try:
        Rule(rule_id=body.rule_id, condition=body.condition, action=body.action)
    except (RuleSyntaxError, ValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid rule: {exc}") from exc

    existing = db.execute(
        select(PolicyRule).where(
            PolicyRule.tenant_id == tenant_id, PolicyRule.rule_id == body.rule_id
        )
    ).scalar_one_or_none()

    if existing is None:
        existing = PolicyRule(tenant_id=tenant_id, rule_id=body.rule_id)
        db.add(existing)

    existing.condition = body.condition
    existing.action = body.action
    existing.description = body.description
    existing.enabled = body.enabled
    db.commit()

    policy_engine.invalidate(tenant_id)
    return {"rule_id": body.rule_id, "stored": True}


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(
    rule_id: str,
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_db),
) -> None:
    from sqlalchemy import delete

    db.execute(
        delete(PolicyRule).where(PolicyRule.tenant_id == tenant_id, PolicyRule.rule_id == rule_id)
    )
    db.commit()
    policy_engine.invalidate(tenant_id)
