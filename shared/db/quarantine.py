"""Cached "which of this model's inputs are quarantined?" lookup, shared by both planes.

Same shape as ``shared/db/registry.py`` and for the same reason: the gateway
reads it on every request, and the control plane must be able to evict it the
moment a person approves a quarantine or its release — otherwise an approved
hold would not take effect until an arbitrary TTL ran out.

A quarantine exists only as an *applied* ``quarantine_input`` remediation.
There is no separate flag to drift out of sync with the record of who approved
it.
"""

from __future__ import annotations

from sqlalchemy import select

from shared.cache import get_cache
from shared.db.models import Remediation
from shared.db.session import session_scope
from shared.telemetry.logging import get_logger

log = get_logger(__name__)

QUARANTINE_TTL_S = 10


def _key(tenant_id: str, model_id: str) -> str:
    return f"custos:quarantine:{tenant_id}:{model_id}"


def active_quarantines(tenant_id: str, model_id: str) -> dict[str, str]:
    """``{input_name: reason}`` for every input currently held. Empty if none.

    Never raises. On a database error it returns no holds, uncached, and logs
    loudly — the same direction as the rest of the hot path (ADR 0001): a
    lookup failure must not turn into a verdict on its own. The drift floor
    still applies, so a model whose feed has died is not waved through by
    this alone.
    """
    cache = get_cache()
    key = _key(tenant_id, model_id)
    cached = cache.get(key)
    if cached is not None:
        return dict(cached)

    try:
        with session_scope() as db:
            rows = db.execute(
                select(Remediation).where(
                    Remediation.tenant_id == tenant_id,
                    Remediation.model_id == model_id,
                    Remediation.action == "quarantine_input",
                    Remediation.status == "applied",
                )
            ).scalars()
            held: dict[str, str] = {}
            for row in rows:
                for name in row.params.get("inputs", []):
                    reason = row.params.get("reasons", {}).get(name, "upstream feed is broken")
                    held[name] = f"{reason}; incident #{row.incident_id}"
    except Exception as exc:
        log.error("quarantine_lookup_failed", extra={"error": f"{type(exc).__name__}: {exc}"})
        return {}

    cache.set(key, held, QUARANTINE_TTL_S)
    return held


def peek_quarantines(tenant_id: str, model_id: str) -> dict[str, str] | None:
    """The cached answer if it can be read without blocking, else None.

    The hot path calls this first so a cache hit costs a dict lookup instead
    of a thread hop. Only the in-process cache qualifies: a Redis read is
    network I/O, and doing it on the event loop is exactly what the gateway
    must never do (see AdmissionGate).
    """
    from shared.cache import _InProcessCache

    cache = get_cache()
    if not isinstance(cache, _InProcessCache):
        return None
    cached = cache.get(_key(tenant_id, model_id))
    return None if cached is None else dict(cached)


def invalidate_quarantines(tenant_id: str, model_id: str) -> None:
    """Evict after a quarantine is applied or released, so it takes effect now."""
    get_cache().delete(_key(tenant_id, model_id))
