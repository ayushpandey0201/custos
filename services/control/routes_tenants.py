"""POST /tenants — bootstrap a tenant and mint its API key.

Split out from routes_config because it is the one endpoint that cannot itself
require an API key: it is where the first key comes from. In a real deployment
this sits behind an operator-only network path or an admin token; that boundary
is deliberately left visible rather than faked with a hardcoded secret.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from services.gateway.auth import generate_api_key, hash_api_key
from shared.config.tenant import TenantConfig
from shared.db.models import Tenant
from shared.db.session import get_db

router = APIRouter(prefix="/tenants", tags=["tenants"])


class CreateTenantRequest(BaseModel):
    tenant_id: str
    name: str = ""


class CreateTenantResponse(BaseModel):
    tenant_id: str
    name: str
    api_key: str
    config: TenantConfig


@router.post("", response_model=CreateTenantResponse, status_code=201)
def create_tenant(body: CreateTenantRequest, db: Session = Depends(get_db)) -> CreateTenantResponse:
    """Create a tenant with default config and return its key.

    The plaintext key is returned exactly once, here. Only its SHA-256 lands in
    the database, so this response is the only opportunity to capture it.
    """
    if db.get(Tenant, body.tenant_id) is not None:
        raise HTTPException(status_code=409, detail=f"tenant {body.tenant_id!r} already exists")

    api_key = generate_api_key()
    config = TenantConfig.default(body.tenant_id)
    stored = config.model_dump()
    stored.pop("tenant_id")

    db.add(
        Tenant(
            tenant_id=body.tenant_id,
            name=body.name or body.tenant_id,
            api_key_hash=hash_api_key(api_key),
            config=stored,
        )
    )
    db.commit()

    return CreateTenantResponse(
        tenant_id=body.tenant_id, name=body.name or body.tenant_id, api_key=api_key, config=config
    )
