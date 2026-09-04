"""API-key middleware -> tenant resolution.

Keys are compared by SHA-256 digest, never in plaintext: the database stores
only the hash, so a dump of the ``tenants`` table does not yield working
credentials. Lookups are cached — this runs on every request and must not cost
a database round-trip.
"""

from __future__ import annotations

import hashlib
import secrets

from fastapi import Header, HTTPException, status

from shared.cache import get_cache

API_KEY_HEADER = "X-API-Key"
_CACHE_TTL_S = 60


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def generate_api_key(prefix: str = "custos") -> str:
    """A fresh key. Returned once at tenant creation and never recoverable."""
    return f"{prefix}_{secrets.token_urlsafe(32)}"


async def resolve_tenant(api_key: str) -> str:
    """Map an API key to its tenant_id.

    Raises:
        PermissionError: if the key matches no tenant.
    """
    if not api_key:
        raise PermissionError("missing API key")

    digest = hash_api_key(api_key)
    cache = get_cache()
    cache_key = f"custos:apikey:{digest}"

    cached = cache.get(cache_key)
    if cached is not None:
        if cached == "":
            # Negative result cached too, so a flood of bad keys cannot be used
            # to hammer the database.
            raise PermissionError("invalid API key")
        return cached

    from sqlalchemy import select

    from shared.db.models import Tenant
    from shared.db.session import session_scope

    with session_scope() as db:
        tenant_id = db.execute(
            select(Tenant.tenant_id).where(Tenant.api_key_hash == digest)
        ).scalar_one_or_none()

    cache.set(cache_key, tenant_id or "", _CACHE_TTL_S)
    if tenant_id is None:
        raise PermissionError("invalid API key")
    return tenant_id


async def require_tenant(x_api_key: str = Header(default="", alias=API_KEY_HEADER)) -> str:
    """FastAPI dependency: resolved tenant_id, or 401."""
    try:
        return await resolve_tenant(x_api_key)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": API_KEY_HEADER},
        ) from exc
