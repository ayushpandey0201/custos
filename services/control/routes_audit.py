"""GET /audit, GET /audit/export, GET /audit/verify."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.gateway import audit
from services.gateway.auth import require_tenant
from shared.db.models import AuditEntry, DecisionLog
from shared.db.session import get_db, session_scope
from shared.timeutil import iso_utc

router = APIRouter(prefix="/audit", tags=["audit"])

# Ceiling on rows examined while filling one filtered page. Bounds the cost of
# a filter that matches nothing without silently returning a short page — the
# response reports when this was hit.
MAX_FILTER_SCAN = 5000


@router.get("")
def list_audit(
    limit: int = Query(default=50, le=500),
    offset: int = 0,
    decision: str | None = None,
    model_id: str | None = None,
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_db),
) -> dict:
    """Page through a tenant's audit chain, newest first.

    ``decision`` and ``model_id`` filter on fields inside the hashed JSON
    payload. Those fields are deliberately *not* mirrored into indexed columns:
    a column beside the payload is not covered by the entry hash, so it could
    disagree with the payload it claims to describe — precisely the ambiguity
    this table exists to eliminate.

    So filtering happens in Python, over a streamed cursor, collecting until the
    page is full rather than filtering a pre-truncated page. ``limit`` therefore
    means "up to this many *matches*", and ``offset`` skips that many matches.
    The scan is capped so an unmatched filter cannot walk an entire chain;
    ``scan_truncated`` in the response says when that cap was hit.
    """
    stmt = (
        select(AuditEntry)
        .where(AuditEntry.tenant_id == tenant_id)
        .order_by(AuditEntry.seq.desc())
        .execution_options(yield_per=200)
    )

    entries: list[dict] = []
    matched = scanned = 0
    truncated = False

    for row in db.execute(stmt).scalars():
        if scanned >= MAX_FILTER_SCAN:
            truncated = True
            break
        scanned += 1

        payload = row.payload or {}
        if decision and payload.get("decision") != decision:
            continue
        if model_id and payload.get("model_id") != model_id:
            continue

        matched += 1
        if matched <= offset:
            continue

        entries.append(
            {
                "seq": row.seq,
                "entry_hash": row.entry_hash,
                "prev_hash": row.prev_hash,
                "trace_id": row.trace_id,
                "created_at": iso_utc(row.created_at),
                "payload": payload,
            }
        )
        if len(entries) >= limit:
            break

    return {
        "entries": entries,
        "limit": limit,
        "offset": offset,
        "scanned": scanned,
        "scan_truncated": truncated,
    }


@router.get("/verify")
def verify(tenant_id: str = Depends(require_tenant)) -> dict:
    """Recompute the whole chain and report the first break, if any.

    This is the endpoint that makes the audit log worth having: without it the
    hashes are decoration.
    """
    return audit.verify_chain(tenant_id)


@router.get("/export")
def export(tenant_id: str = Depends(require_tenant)) -> StreamingResponse:
    """Stream the full chain as JSON Lines.

    Streamed rather than assembled: an evidence export covers the whole history
    by definition, and buffering it would put an unbounded amount of a tenant's
    audit log in memory.
    """

    def rows():
        with session_scope() as db:
            stmt = (
                select(AuditEntry)
                .where(AuditEntry.tenant_id == tenant_id)
                .order_by(AuditEntry.seq)
                .execution_options(yield_per=200)
            )
            for row in db.execute(stmt).scalars():
                yield (
                    json.dumps(
                        {
                            "seq": row.seq,
                            "prev_hash": row.prev_hash,
                            "entry_hash": row.entry_hash,
                            "payload": row.payload,
                        },
                        default=str,
                    )
                    + "\n"
                )

    return StreamingResponse(
        rows(),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="custos-audit-{tenant_id}.jsonl"'},
    )


@router.get("/decisions")
def recent_decisions(
    limit: int = Query(default=50, le=500),
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Denormalised decision stream for the dashboard."""
    rows = db.execute(
        select(DecisionLog)
        .where(DecisionLog.tenant_id == tenant_id)
        .order_by(DecisionLog.created_at.desc(), DecisionLog.id.desc())
        .limit(limit)
    ).scalars()

    return [
        {
            "id": r.id,
            "model_id": r.model_id,
            "decision": r.decision,
            "trust_score": round(r.trust_score, 4),
            "action": r.action,
            "trace_id": r.trace_id,
            "reasons": r.reasons,
            "latency_ms": round(r.latency_ms, 2),
            "created_at": iso_utc(r.created_at),
        }
        for r in rows
    ]
