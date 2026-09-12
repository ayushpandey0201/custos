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
import random
import time
import zlib
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from shared.db.models import AuditEntry
from shared.db.session import session_scope
from shared.schemas.decision import DecisionRecord
from shared.timeutil import iso_utc

# prev_hash of the first entry in a chain.
GENESIS_HASH = "0" * 64

# On Postgres `_lock_chain` removes the race outright and these are never
# needed. On SQLite they are the whole defence, which is why there are more of
# them than there used to be and why they back off: a dropped append is a
# decision with no evidence, and `_write_audit` cannot tell the difference
# between that and a decision that was never made.
_MAX_APPEND_RETRIES = 12
_BACKOFF_BASE_S = 0.002
# Uncapped, doubling twelve times would let one unlucky append block its caller
# for several seconds — far past the request's whole latency budget. Capped,
# the worst case across all attempts is well under a second.
_BACKOFF_MAX_S = 0.05


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


def _lock_chain(db: Session, tenant_id: str) -> None:
    """Serialise appends to one tenant's chain for the rest of this transaction.

    Allocating ``seq`` means reading the current head and then inserting
    ``head + 1``. Those are two statements, so without a lock two appenders
    read the same head and one of them loses — and losing means the entry is
    *dropped*, because ``_write_audit`` treats a failed append as non-fatal.

    A process-local lock is not enough. In a single-worker gateway the event
    loop already serialises these writes, so an in-process lock would be
    protecting a path that is not racing; the race appears precisely when the
    gateway is scaled out to several workers, and by then the contending
    appenders are in different processes and cannot see each other's locks.
    Measured through the real gateway: 0 entries lost of 1200 at one worker,
    2 lost at four. So the lock has to live where all the workers meet, which
    is the database.

    The lock is taken *before* the head is read, which is the whole point — a
    lock acquired after the read would serialise nothing.

    Postgres gets a real lock. SQLite gets nothing here and relies on the
    retry loop instead: forcing ``BEGIN IMMEDIATE`` would mean either raw SQL
    inside a transaction SQLAlchemy is already managing (an error) or an
    engine-wide event hook that makes *every* transaction take a write lock,
    including the read-only ones on the control plane. SQLite is the
    single-node backend, where one uvicorn worker means the event loop
    serialises these writes anyway; Postgres is what runs multi-worker, and
    Postgres is where the race is reachable.
    """
    if db.get_bind().dialect.name != "postgresql":
        return

    # Advisory lock keyed on the tenant, released automatically at commit or
    # rollback. Per-tenant rather than global so one busy tenant's appends do
    # not serialise every other tenant's. crc32 is offset into the signed
    # 64-bit range pg_advisory_xact_lock expects.
    key = zlib.crc32(tenant_id.encode("utf-8")) - 2**31
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def append_to_chain(record: dict, tenant_id: str | None = None) -> str:
    """Append a payload to a tenant's chain. Returns the new entry hash."""
    tenant = tenant_id or record.get("tenant_id")
    if not tenant:
        raise ValueError("append_to_chain requires a tenant_id")

    last_error: Exception | None = None
    for attempt in range(_MAX_APPEND_RETRIES):
        try:
            with session_scope() as db:
                _lock_chain(db, tenant)
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
        except (IntegrityError, OperationalError) as exc:
            # IntegrityError: lost the race for this seq.
            # OperationalError: SQLite's writer lock was held past its timeout.
            # Both mean "someone else got there first", and both are retryable.
            last_error = exc
            _backoff(attempt)

    raise RuntimeError(
        f"could not append to audit chain after {_MAX_APPEND_RETRIES} attempts"
    ) from last_error


def _backoff(attempt: int) -> None:
    """Randomised exponential backoff between append attempts.

    Retrying immediately is what made the original five attempts insufficient:
    every loser of a race re-reads the head at the same moment and collides
    with the same peers again, so the contenders stay in lockstep and burn all
    their attempts in a few microseconds. Jitter is what actually breaks the
    tie — the exponential part only keeps the wait bounded as contention rises.

    This blocks, which is deliberate. ``append_to_chain`` is called
    synchronously from the request path, so the alternative to a brief sleep is
    returning a decision with no evidence behind it.
    """
    time.sleep(random.uniform(0, min(_BACKOFF_MAX_S, _BACKOFF_BASE_S * (2**attempt))))


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
