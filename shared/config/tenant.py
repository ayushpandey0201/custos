"""TenantConfig model + cached loader.

Read on every gateway request, written only through ``PUT /config`` on the
control plane. Cached with a short TTL so a config change takes effect within
seconds without adding a database round-trip to the hot path.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from shared.cache import get_cache
from shared.config import defaults


class TenantConfig(BaseModel):
    """Everything a tenant can tune about how their traffic is judged."""

    tenant_id: str
    enabled_engines: list[str] = Field(default_factory=lambda: list(defaults.DEFAULT_ENGINES))
    weights: dict[str, float] = Field(default_factory=lambda: dict(defaults.DEFAULT_WEIGHTS))
    thresholds: dict[str, float] = Field(default_factory=lambda: dict(defaults.DEFAULT_THRESHOLDS))
    fail_open: bool = defaults.FAIL_OPEN

    @field_validator("thresholds")
    @classmethod
    def _block_below_review(cls, v: dict[str, float]) -> dict[str, float]:
        """Reject a threshold pair that would make REVIEW unreachable.

        Caught here rather than at decision time: a nonsensical config should
        fail loudly on the cold write path, not silently distort verdicts on
        the hot one.
        """
        block, review = v.get("block", 0.0), v.get("review", 1.0)
        if block > review:
            raise ValueError(f"block threshold ({block}) must not exceed review ({review})")
        return v

    def weight_for(self, engine: str) -> float:
        return self.weights.get(engine, 0.0)

    @classmethod
    def default(cls, tenant_id: str) -> TenantConfig:
        return cls(tenant_id=tenant_id)


def _cache_key(tenant_id: str) -> str:
    return f"custos:tenant_config:{tenant_id}"


def load_tenant_config(tenant_id: str) -> TenantConfig:
    """Return a tenant's config, from cache when warm.

    Falls back to defaults for an unknown or unconfigured tenant rather than
    raising: a missing config row is a configuration gap, not a reason to fail
    live traffic.
    """
    cache = get_cache()
    cached = cache.get(_cache_key(tenant_id))
    if cached is not None:
        return TenantConfig(**cached)

    config = _load_from_db(tenant_id)
    cache.set(_cache_key(tenant_id), config.model_dump(), defaults.TENANT_CONFIG_TTL_S)
    return config


def _load_from_db(tenant_id: str) -> TenantConfig:
    from shared.db.models import Tenant
    from shared.db.session import session_scope

    try:
        with session_scope() as db:
            tenant = db.get(Tenant, tenant_id)
            if tenant is None or not tenant.config:
                return TenantConfig.default(tenant_id)
            return TenantConfig(tenant_id=tenant_id, **tenant.config)
    except Exception:
        return TenantConfig.default(tenant_id)


def invalidate_tenant_config(tenant_id: str) -> None:
    """Evict after a config write so the change is visible immediately."""
    get_cache().delete(_cache_key(tenant_id))
