"""Cached "is this model registered?" lookup, shared by both planes.

Lives in ``shared/`` rather than in the gateway because both planes need it and
they must agree: the gateway *reads* it on every request, and the control plane
*invalidates* it the moment a model is registered. If the write side could not
reach the same cache key, a freshly registered model would keep routing to
REVIEW until an arbitrary TTL expired.
"""

from __future__ import annotations

from sqlalchemy import select

from shared.cache import get_cache
from shared.db.models import Model
from shared.db.session import session_scope

# Short, because it bounds the only cost of being stale: a model registered a
# moment ago still reading as unknown. That is a safe direction to be wrong in
# (REVIEW, not ALLOW), and invalidation makes it rare anyway.
MODEL_REGISTRY_TTL_S = 10


def _key(tenant_id: str, model_id: str) -> str:
    return f"custos:model_known:{tenant_id}:{model_id}"


def is_model_registered(tenant_id: str, model_id: str) -> bool:
    """Whether ``model_id`` is registered for ``tenant_id``.

    Unknown models route to REVIEW (ADR 0005), so this runs on the hot path and
    is cached like every other read there — registration changes at human speed,
    and an uncached lookup would cost a database round-trip per request to
    re-learn a fact that has not changed in weeks.

    Never raises. On a database error it returns True, degrading to "assume
    registered" so that the engines' own signals stay in charge rather than
    every request flipping to REVIEW because one lookup failed.
    """
    cache = get_cache()
    key = _key(tenant_id, model_id)

    cached = cache.get(key)
    if cached is not None:
        return bool(cached)

    try:
        with session_scope() as db:
            known = (
                db.execute(
                    select(Model.id).where(Model.tenant_id == tenant_id, Model.model_id == model_id)
                ).first()
                is not None
            )
    except Exception:
        # Deliberately not cached: the next request should retry the database
        # rather than inherit a guess for the whole TTL.
        return True

    cache.set(key, known, MODEL_REGISTRY_TTL_S)
    return known


def invalidate_model_registration(tenant_id: str, model_id: str) -> None:
    """Evict after registering a model, so it is trusted immediately."""
    get_cache().delete(_key(tenant_id, model_id))
