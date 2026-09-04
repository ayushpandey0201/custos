"""Build audit record, hash chain it, enqueue to audit writer.

Every decision is appended to a per-tenant hash chain:

    entry_hash = SHA256( prev_hash || canonical_json(payload) )

Each entry commits to its predecessor, so editing any historical row changes
its hash and breaks every link after it. That does not make the log
*tamper-proof* — anyone with database access can rewrite rows — it makes it
tamper-*evident*, which is the property an auditor actually needs: not "this
cannot be changed" but "I can prove whether it was."

``GET /audit/verify`` recomputes the chain and reports the first broken
sequence number, which localises tampering rather than just detecting it.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.db.models import AuditEntry
from shared.db.session import session_scope
from shared.schemas.decision import DecisionRecord
from shared.timeutil import iso_utc

# prev_hash of the first entry in a chain.
GENESIS_HASH = "0" * 64

# Concurrent appends race for the same sequence number. The unique constraint
# on (tenant_id, seq) turns that race into an IntegrityError, which we retry.
_MAX_APPEND_RETRIES = 5


def canonical_json(payload: dict) -> str:
    """Deterministic JSON: sorted keys, no incidental whitespace.

    The hash is only meaningful if a given payload always serialises to exactly
    the same bytes — otherwise dict ordering alone would look like tampering.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_hash(prev_hash: str, payload: dict) -> str:
    return hashlib.sha256((prev_hash + canonical_json(payload)).encode("utf-8")).hexdigest()


def build_record(decision: DecisionRecord, context: dict[str, Any] | None = None) -> dict:
    """Assemble the payload that gets hashed.

    Contains the verdict, the score, and each engine's evidence — enough for an
    auditor to reconstruct *why* without replaying the request. Deliberately
    excludes raw feature values: those are the caller's customer data, and an
    append-only log is the last place it should be duplicated.
    """
    payload = {
        "tenant_id": decision.tenant_id,
        "model_id": decision.model_id,
        "action": decision.action,
        "decision": decision.decision.value,
        "trust_score": round(decision.trust_score, 6),
        "reasons": decision.reasons,
        "signals": decision.signals,
        "degraded_engines": decision.degraded_engines,
        "trace_id": decision.trace_id,
        "created_at": iso_utc(decision.created_at),
    }
    if context:
        payload["context"] = context
    return payload


def append_to_chain(record: dict, tenant_id: str | None = None) -> str:
    """Append a payload to a tenant's chain. Returns the new entry hash."""
    tenant = tenant_id or record.get("tenant_id")
    if not tenant:
        raise ValueError("append_to_chain requires a tenant_id")

    last_error: Exception | None = None
    for _ in range(_MAX_APPEND_RETRIES):
        try:
            with session_scope() as db:
                seq, prev_hash = _chain_head(db, tenant)
                entry_hash = compute_hash(prev_hash, record)
                db.add(
                    AuditEntry(
                        tenant_id=tenant,
                        seq=seq + 1,
                        prev_hash=prev_hash,
                        entry_hash=entry_hash,
                        payload=record,
                        trace_id=record.get("trace_id", ""),
                    )
                )
            return entry_hash
        except IntegrityError as exc:
            # Lost the race for this seq. Re-read the head and try again.
            last_error = exc

    raise RuntimeError(
        f"could not append to audit chain after {_MAX_APPEND_RETRIES} attempts"
    ) from last_error


def _chain_head(db: Session, tenant_id: str) -> tuple[int, str]:
    """Current (seq, entry_hash) of a tenant's chain, or (0, GENESIS)."""
    max_seq = db.execute(
        select(func.max(AuditEntry.seq)).where(AuditEntry.tenant_id == tenant_id)
    ).scalar()
    if max_seq is None:
        return 0, GENESIS_HASH

    head = db.execute(
        select(AuditEntry).where(AuditEntry.tenant_id == tenant_id, AuditEntry.seq == max_seq)
    ).scalar_one()
    return max_seq, head.entry_hash


def verify_chain(tenant_id: str) -> dict:
    """Recompute a tenant's chain end to end.

    Returns:
        ``{"valid": bool, "entries": int, "broken_at": int | None, "detail": str}``
        where ``broken_at`` is the sequence number of the first entry whose
        recomputed hash does not match what was stored.
    """
    with session_scope() as db:
        entries = list(
            db.execute(
                select(AuditEntry).where(AuditEntry.tenant_id == tenant_id).order_by(AuditEntry.seq)
            ).scalars()
        )

    if not entries:
        return {"valid": True, "entries": 0, "broken_at": None, "detail": "chain is empty"}

    prev_hash = GENESIS_HASH
    for position, entry in enumerate(entries, start=1):
        if entry.seq != position:
            return {
                "valid": False,
                "entries": len(entries),
                "broken_at": entry.seq,
                "detail": f"sequence gap: expected seq {position}, found {entry.seq}",
            }
        if entry.prev_hash != prev_hash:
            return {
                "valid": False,
                "entries": len(entries),
                "broken_at": entry.seq,
                "detail": f"entry {entry.seq} does not link to its predecessor",
            }
        expected = compute_hash(prev_hash, entry.payload)
        if expected != entry.entry_hash:
            return {
                "valid": False,
                "entries": len(entries),
                "broken_at": entry.seq,
                "detail": f"payload of entry {entry.seq} was modified after it was written",
            }
        prev_hash = entry.entry_hash

    return {
        "valid": True,
        "entries": len(entries),
        "broken_at": None,
        "detail": f"all {len(entries)} entries verified",
    }
