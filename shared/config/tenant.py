"""TenantConfig model + Redis-cached loader."""

from pydantic import BaseModel


class TenantConfig(BaseModel):
    tenant_id: str
    enabled_engines: list[str]
    weights: dict[str, float]
    thresholds: dict[str, float]


def load_tenant_config(tenant_id: str) -> TenantConfig:
    raise NotImplementedError

