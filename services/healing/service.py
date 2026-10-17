"""The governed self-healing loop, as a state machine with evidence.

    detect ──▶ diagnose ──▶ propose ──▶ shadow test ──▶ human approves ──▶ apply ──▶ verify
                                                 └──▶ human rejects

Incident: open ──▶ resolved
Remediation: proposed ──▶ approved ──▶ applied ──▶ (released | rolled_back | failed_verification)
                     ├──▶ rejected
                     └──▶ superseded   (a sibling proposal was approved instead)

What Custos may repair is limited to what it controls: how it gates the model's
decisions. The repairs, by diagnosis:

  pipeline_break    quarantine_input — hold every decision for the model until
                    the feed is fixed; then release_input, approved separately.
                    Re-baselining is deliberately *withheld*: learning a new
                    reference from a broken feed would teach the drift alarm
                    that broken data is normal.
  population_shift  rebaseline — accept the shifted population as the new
                    reference (undoable, via rollback_baseline), or
                    request_retrain — a recorded request to the model's owner,
                    because Custos cannot retrain a model it does not own.

Three properties hold throughout, and are tested (tests/integration/test_healing.py):

  1. No repair changes a verdict until a named person approves it.
  2. A repair whose shadow test failed cannot be approved.
  3. Every transition is appended to the tenant's hash chain, so the record of
     who approved what, on which evidence, is as tamper-evident as the
     decisions themselves.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

from sqlalchemy import select

from engines.drift import worker
from engines.drift.severity import compute_severity, severity_band
from services.gateway import audit
from services.healing import shadow
from services.healing.diagnose import Diagnosis, diagnose
from shared.db.models import FeatureSample, Incident, Model, Remediation
from shared.db.quarantine import active_quarantines, invalidate_quarantines
from shared.db.session import session_scope
from shared.telemetry.logging import get_logger
from shared.timeutil import iso_utc

log = get_logger(__name__)

# Diagnosis looks at the most recent requests, not a whole day. A feed breaks
# all at once; averaged over 24 hours it would take most of a day to dominate
# the window, and every decision in between would be scored on garbage.
DIAGNOSIS_WINDOW = 200

# A proposed new reference is built from more traffic than diagnosis needs,
# because it will be measured against for a long time.
REBASELINE_WINDOW = 400

# State transitions are read-check-write. The control plane is one process, so
# a process lock is enough to stop two approvals of the same proposal racing.
_LOCK = threading.Lock()


class NotFound(LookupError):
    pass


class Conflict(RuntimeError):
    pass


# --- reading ----------------------------------------------------------------


def recent_rows(tenant_id: str, model_id: str, n: int = DIAGNOSIS_WINDOW) -> list[dict]:
    """The model's ``n`` most recent feature vectors since its reference was set, oldest first.

    Only traffic that arrived after the current baseline counts. That is what
    makes verification honest: after a re-baseline, the traffic the new
    reference was built from would trivially "verify" it, so the repair is
    judged only on requests that came in afterwards.
    """
    with session_scope() as db:
        baseline_at = db.execute(
            select(Model.baseline_at).where(
                Model.tenant_id == tenant_id, Model.model_id == model_id
            )
        ).scalar_one_or_none()
        stmt = select(FeatureSample.features).where(
            FeatureSample.tenant_id == tenant_id, FeatureSample.model_id == model_id
        )
        if baseline_at is not None:
            stmt = stmt.where(FeatureSample.created_at >= baseline_at)
        rows = list(db.execute(stmt.order_by(FeatureSample.id.desc()).limit(n)).scalars())
    rows.reverse()
    return rows


def _window_start(tenant_id: str, model_id: str, n: int = DIAGNOSIS_WINDOW) -> str | None:
    """When the oldest request in the current diagnosis window arrived."""
    with session_scope() as db:
        stamps = list(
            db.execute(
                select(FeatureSample.created_at)
                .where(FeatureSample.tenant_id == tenant_id, FeatureSample.model_id == model_id)
                .order_by(FeatureSample.id.desc())
                .limit(n)
            ).scalars()
        )
    return iso_utc(stamps[-1]) if stamps else None


def _baseline(tenant_id: str, model_id: str) -> dict[str, list[float]] | None:
    with session_scope() as db:
        model = db.execute(
            select(Model).where(Model.tenant_id == tenant_id, Model.model_id == model_id)
        ).scalar_one_or_none()
        return None if model is None else model.baseline


def _diagnose_now(tenant_id: str, model_id: str) -> Diagnosis:
    return diagnose(_baseline(tenant_id, model_id) or {}, recent_rows(tenant_id, model_id))


# --- evidence ---------------------------------------------------------------


def _record(
    tenant_id: str,
    model_id: str,
    event: str,
    incident_id: int,
    *,
    remediation_id: int | None = None,
    action: str | None = None,
    actor: str = "custos",
    detail: dict | None = None,
) -> str:
    """Append one healing event to the tenant's audit chain."""
    payload = {
        "type": "healing",
        "event": event,
        "tenant_id": tenant_id,
        "model_id": model_id,
        "incident_id": incident_id,
        "remediation_id": remediation_id,
        "action": action,
        "actor": actor,
        "detail": detail or {},
        "trace_id": f"incident-{incident_id}",
        "created_at": iso_utc(datetime.now(UTC)),
    }
    return audit.append_to_chain(payload, tenant_id)


# --- proposals --------------------------------------------------------------


def _propose_quarantine(diagnosis: Diagnosis, tenant_id: str, model_id: str) -> dict:
    broken = diagnosis.broken
    names = [i.name for i in broken]
    held = {**active_quarantines(tenant_id, model_id), **{i.name: i.detail for i in broken}}
    impact = shadow.replay(tenant_id, model_id, quarantined=held)
    return {
        "action": "quarantine_input",
        "params": {"inputs": names, "reasons": {i.name: i.detail for i in broken}},
        "rationale": (
            f"Hold every decision for this model for human review until the "
            f"{', '.join(names)} feed is repaired. The model is still answering, and its "
            "scores look normal, but it is scoring on an input that carries no information — "
            "these are not the decisions it was validated to make."
        ),
        "shadow": {
            "passed": True,
            "checks": [f"{i.name}: {i.detail}" for i in broken],
            "impact": impact,
            "summary": (
                f"Of the last {impact['replayed']} decisions, {impact['changed']} would have "
                "been held for review instead."
            ),
        },
    }


def _propose_release(
    tenant_id: str, model_id: str, inputs: list[str], diagnosis: Diagnosis
) -> dict:
    remaining = {
        k: v for k, v in active_quarantines(tenant_id, model_id).items() if k not in inputs
    }
    # Releasing also re-measures drift on the verified-healthy window (see
    # _apply), so replay with that reading rather than the one recorded while
    # the feed was broken — otherwise the broken period's drift would hide
    # most of what the release actually changes.
    impact = shadow.replay(
        tenant_id, model_id, quarantined=remaining, drift_severity=diagnosis.severity
    )
    healthy = {i.name for i in diagnosis.inputs if i.status in ("ok", "shifted")}
    still_broken = [n for n in inputs if n not in healthy]
    return {
        "action": "release_input",
        "params": {"inputs": inputs, "healthy_since": _window_start(tenant_id, model_id)},
        "rationale": (
            f"The {', '.join(inputs)} feed is arriving normally again in the last "
            f"{diagnosis.window} requests. Release the hold so decisions are gated normally."
        ),
        "shadow": {
            "passed": not still_broken,
            "checks": [f"{n}: arriving normally" for n in inputs if n not in still_broken]
            + [f"{n}: still broken" for n in still_broken],
            "impact": impact,
            "summary": (
                f"Of the last {impact['replayed']} decisions, {impact['changed']} would no "
                "longer be held."
            ),
        },
    }


def _candidate_baseline(tenant_id: str, model_id: str) -> tuple[dict[str, list[float]], dict]:
    """A new reference from recent traffic, and the evidence on whether it is safe.

    The test is a hold-out: build a reference from the older half of the
    window and score the newer half against it. If the population has
    settled, the newer half looks like the older one. If it is still moving,
    it does not — and re-baselining now would hide drift that is still
    happening, which is the failure the fixed baseline exists to prevent.
    """
    rows = recent_rows(tenant_id, model_id, REBASELINE_WINDOW)
    candidate = worker._columnar(rows)
    checks: list[str] = []
    passed = True

    current = _baseline(tenant_id, model_id) or {}
    window_diagnosis = diagnose(current, rows)
    if window_diagnosis.broken:
        passed = False
        checks.append(
            "refused: the window contains a broken input ("
            + ", ".join(f"{i.name} {i.detail}" for i in window_diagnosis.broken)
            + "); a reference learned from it would make broken data look normal"
        )

    held_out = None
    if len(rows) < 2 * 60:
        passed = False
        checks.append(f"only {len(rows)} recent requests; at least 120 are needed to test")
    else:
        half = len(rows) // 2
        older, newer = worker._columnar(rows[:half]), worker._columnar(rows[half:])
        per_feature = worker.score_features(older, newer)
        held_out = compute_severity({n: s["severity"] for n, s in per_feature.items()})
        band = severity_band(held_out)
        if band == "significant":
            passed = False
            checks.append(
                f"refused: the newer half of the window drifts {held_out:.2f} from the older "
                "half — the population is still moving, and a new reference would hide it"
            )
        else:
            checks.append(
                f"settled: the newer half scores {held_out:.2f} against a reference built from "
                "the older half — below the significant line (0.67); with a few hundred "
                "requests, sampling noise alone reads around 0.3"
            )
    return candidate, {"passed": passed, "checks": checks, "held_out_severity": held_out}


def _propose_rebaseline(tenant_id: str, model_id: str) -> dict:
    candidate, evidence = _candidate_baseline(tenant_id, model_id)
    held_out = evidence["held_out_severity"]
    impact = (
        shadow.replay(
            tenant_id,
            model_id,
            quarantined=active_quarantines(tenant_id, model_id),
            drift_severity=held_out,
        )
        if held_out is not None
        else {"replayed": 0, "changed": 0, "transitions": {}, "examples": []}
    )
    return {
        "action": "rebaseline",
        "params": {
            "baseline": candidate,
            "window": max((len(v) for v in candidate.values()), default=0),
        },
        "rationale": (
            "Accept the shifted population as the new reference for drift. Right only if the "
            "shift is real and expected — a new market, a pricing change — and the model still "
            "performs on it. Custos cannot know that; it is the reviewer's call. Undoable."
        ),
        "shadow": {
            **evidence,
            "impact": impact,
            "summary": (
                f"Of the last {impact['replayed']} decisions, {impact['changed']} would have had "
                "a different verdict against the new reference."
            ),
        },
    }


def _propose_retrain(diagnosis: Diagnosis) -> dict:
    names = [i.name for i in diagnosis.shifted]
    return {
        "action": "request_retrain",
        "params": {"inputs": names, "severity": diagnosis.severity},
        "rationale": (
            "Ask the model's owner to retrain on recent data. Custos cannot retrain a model it "
            "does not own; approving this records the request, with the evidence, on the audit "
            "chain. Decisions stay under the drift floor until a new model and baseline ship."
        ),
        "shadow": {
            "passed": True,
            "checks": ["changes no verdicts by itself"],
            "impact": {"replayed": 0, "changed": 0, "transitions": {}, "examples": []},
            "summary": "No verdicts change until the owner ships a retrained model.",
        },
    }


def _propose_rollback(tenant_id: str, model_id: str, target: Remediation) -> dict:
    previous = (target.undo or {}).get("baseline") or {}
    live = worker._columnar(recent_rows(tenant_id, model_id))
    per_feature = worker.score_features(previous, live)
    severity = compute_severity({n: s["severity"] for n, s in per_feature.items()})
    impact = shadow.replay(
        tenant_id,
        model_id,
        quarantined=active_quarantines(tenant_id, model_id),
        drift_severity=severity,
    )
    return {
        "action": "rollback_baseline",
        "params": {"target": target.id},
        "rationale": (
            "The new reference did not hold: recent traffic has moved away from it too. Restore "
            "the reference that was in force before, so drift is measured against what the "
            "model was validated on."
        ),
        "shadow": {
            "passed": bool(previous),
            "checks": [f"against the previous reference, recent traffic scores {severity:.2f}"],
            "impact": impact,
            "summary": (
                f"Of the last {impact['replayed']} decisions, {impact['changed']} would have had "
                "a different verdict."
            ),
        },
    }


def _add_proposal(db, incident: Incident, proposal: dict) -> Remediation:
    row = Remediation(
        incident_id=incident.id,
        tenant_id=incident.tenant_id,
        model_id=incident.model_id,
        action=proposal["action"],
        params=proposal["params"],
        rationale=proposal["rationale"],
        shadow=proposal["shadow"],
        status="proposed",
    )
    db.add(row)
    db.flush()
    return row


def _record_proposal(row: Remediation) -> None:
    _record(
        row.tenant_id,
        row.model_id,
        "remediation_proposed",
        row.incident_id,
        remediation_id=row.id,
        action=row.action,
        detail={
            "rationale": row.rationale,
            "shadow_passed": row.shadow.get("passed"),
            "shadow_checks": row.shadow.get("checks", []),
            "impact": {
                k: row.shadow.get("impact", {}).get(k)
                for k in ("replayed", "changed", "transitions")
            },
        },
    )


# --- detect + diagnose -------------------------------------------------------


def scan(tenant_id: str, model_id: str) -> dict:
    """Verify open incidents, then detect anything new.

    At most one open incident per model *per kind*. Repeated scans verify an
    open incident rather than duplicating it, which is what lets this run
    after every drift recompute without flooding the review queue. But a
    different kind of fault always gets its own incident: a feed that breaks
    while a population-shift incident is open must not hide behind it.
    """
    with _LOCK:
        with session_scope() as db:
            open_ids = list(
                db.execute(
                    select(Incident.id)
                    .where(
                        Incident.tenant_id == tenant_id,
                        Incident.model_id == model_id,
                        Incident.status == "open",
                    )
                    .order_by(Incident.id.desc())
                ).scalars()
            )
        verified = [_verify_locked(tenant_id, i) for i in open_ids]
        still_open = {v["incident"]["kind"] for v in verified if v["incident"]["status"] == "open"}

        if not _baseline(tenant_id, model_id):
            return {"incident": None, "detail": "model has no baseline to diagnose against"}

        diagnosis = _diagnose_now(tenant_id, model_id)
        if (
            diagnosis.kind not in ("pipeline_break", "population_shift")
            or diagnosis.kind in still_open
        ):
            if verified:
                return verified[0]
            return {"incident": None, "diagnosis": diagnosis.to_dict()}

        if diagnosis.kind == "pipeline_break":
            proposals = [_propose_quarantine(diagnosis, tenant_id, model_id)]
            withheld = [
                {
                    "action": "rebaseline",
                    "why": "a reference learned from a broken feed would make broken data look "
                    "normal",
                }
            ]
        else:
            proposals = [_propose_rebaseline(tenant_id, model_id), _propose_retrain(diagnosis)]
            withheld = []

        with session_scope() as db:
            incident = Incident(
                tenant_id=tenant_id,
                model_id=model_id,
                kind=diagnosis.kind,
                summary=diagnosis.summary,
                diagnosis={**diagnosis.to_dict(), "withheld": withheld},
            )
            db.add(incident)
            db.flush()
            rows = [_add_proposal(db, incident, p) for p in proposals]
            incident_id = incident.id

        _record(
            tenant_id,
            model_id,
            "incident_opened",
            incident_id,
            detail={
                "kind": diagnosis.kind,
                "summary": diagnosis.summary,
                "inputs": [
                    {"name": i.name, "status": i.status, "detail": i.detail}
                    for i in diagnosis.inputs
                    if i.status != "ok"
                ],
                "withheld": withheld,
            },
        )
        for row in rows:
            _record_proposal(row)

        log.warning(
            "incident_opened",
            extra={"tenant_id": tenant_id, "model_id": model_id, "kind": diagnosis.kind},
        )
        return {"incident": get_incident(tenant_id, incident_id), "new": True}


# --- human decisions ---------------------------------------------------------


def _load(db, tenant_id: str, remediation_id: int) -> tuple[Remediation, Incident]:
    row = db.get(Remediation, remediation_id)
    if row is None or row.tenant_id != tenant_id:
        raise NotFound(f"remediation {remediation_id} not found")
    incident = db.get(Incident, row.incident_id)
    return row, incident


def approve(tenant_id: str, remediation_id: int, approver: str, note: str = "") -> dict:
    """A named person authorises a repair; Custos applies it and records both."""
    approver = approver.strip()
    if not approver:
        raise Conflict("an approval must name the person approving it")

    with _LOCK:
        with session_scope() as db:
            row, incident = _load(db, tenant_id, remediation_id)
            if row.status != "proposed":
                raise Conflict(f"remediation {remediation_id} is {row.status}, not proposed")
            if incident.status != "open":
                raise Conflict(f"incident {incident.id} is already {incident.status}")
            if not row.shadow.get("passed"):
                raise Conflict(
                    "this repair failed its shadow test and cannot be approved: "
                    + "; ".join(row.shadow.get("checks", []))
                )
            row.status = "approved"
            row.decided_by = approver
            row.decision_note = note
            row.decided_at = datetime.now(UTC)
            action, model_id, incident_id = row.action, row.model_id, incident.id

        _record(
            tenant_id,
            model_id,
            "remediation_approved",
            incident_id,
            remediation_id=remediation_id,
            action=action,
            actor=approver,
            detail={"note": note},
        )
        detail = _apply(tenant_id, remediation_id)
        _record(
            tenant_id,
            model_id,
            "remediation_applied",
            incident_id,
            remediation_id=remediation_id,
            action=action,
            detail=detail,
        )
        return get_incident(tenant_id, incident_id)


def reject(tenant_id: str, remediation_id: int, approver: str, note: str = "") -> dict:
    approver = approver.strip()
    if not approver:
        raise Conflict("a rejection must name the person rejecting it")
    with _LOCK:
        with session_scope() as db:
            row, incident = _load(db, tenant_id, remediation_id)
            if row.status != "proposed":
                raise Conflict(f"remediation {remediation_id} is {row.status}, not proposed")
            row.status = "rejected"
            row.decided_by = approver
            row.decision_note = note
            row.decided_at = datetime.now(UTC)
            action, model_id, incident_id = row.action, row.model_id, incident.id
        _record(
            tenant_id,
            model_id,
            "remediation_rejected",
            incident_id,
            remediation_id=remediation_id,
            action=action,
            actor=approver,
            detail={"note": note},
        )
        return get_incident(tenant_id, incident_id)


def close(tenant_id: str, incident_id: int, approver: str, note: str = "") -> dict:
    """A person closes an incident without a repair — a false alarm, or fixed elsewhere.

    Refused while a quarantine is in force: closing the incident would leave a
    hold with nothing left to release it.
    """
    approver = approver.strip()
    if not approver:
        raise Conflict("closing an incident must name the person closing it")
    with _LOCK:
        with session_scope() as db:
            incident = db.get(Incident, incident_id)
            if incident is None or incident.tenant_id != tenant_id:
                raise NotFound(f"incident {incident_id} not found")
            if incident.status != "open":
                raise Conflict(f"incident {incident_id} is already {incident.status}")
            rows = list(
                db.execute(
                    select(Remediation).where(Remediation.incident_id == incident_id)
                ).scalars()
            )
            if any(r.action == "quarantine_input" and r.status == "applied" for r in rows):
                raise Conflict("an input is still quarantined; approve its release first")
            for r in rows:
                if r.status == "proposed":
                    r.status = "superseded"
            incident.status = "resolved"
            incident.resolved_at = datetime.now(UTC)
            model_id = incident.model_id
        _record(
            tenant_id,
            model_id,
            "incident_closed",
            incident_id,
            actor=approver,
            detail={"note": note},
        )
        return get_incident(tenant_id, incident_id)


def retest(tenant_id: str, remediation_id: int) -> dict:
    """Re-run a pending proposal's shadow test on current traffic.

    A rebaseline refused because the population was still moving may pass an
    hour later. Re-testing rebuilds the candidate from the current window, so
    what gets approved is always what was most recently tested.
    """
    with _LOCK:
        with session_scope() as db:
            row, incident = _load(db, tenant_id, remediation_id)
            if row.status != "proposed":
                raise Conflict(f"remediation {remediation_id} is {row.status}, not proposed")
            action, model_id, incident_id = row.action, row.model_id, incident.id
            target = (
                db.get(Remediation, row.params.get("target"))
                if action == "rollback_baseline"
                else None
            )

        diagnosis = _diagnose_now(tenant_id, model_id)
        if action == "quarantine_input":
            if not diagnosis.broken:
                raise Conflict("no input is broken any more; there is nothing to quarantine")
            proposal = _propose_quarantine(diagnosis, tenant_id, model_id)
        elif action == "release_input":
            with session_scope() as db:
                inputs = db.get(Remediation, remediation_id).params["inputs"]
            proposal = _propose_release(tenant_id, model_id, inputs, diagnosis)
        elif action == "rebaseline":
            proposal = _propose_rebaseline(tenant_id, model_id)
        elif action == "rollback_baseline" and target is not None:
            proposal = _propose_rollback(tenant_id, model_id, target)
        else:
            proposal = _propose_retrain(diagnosis)

        with session_scope() as db:
            row = db.get(Remediation, remediation_id)
            row.params = proposal["params"]
            row.shadow = proposal["shadow"]
            row.rationale = proposal["rationale"]
        with session_scope() as db:
            _record_proposal(db.get(Remediation, remediation_id))
        return get_incident(tenant_id, incident_id)


# --- apply -------------------------------------------------------------------


def _apply(tenant_id: str, remediation_id: int) -> dict:
    """Make an approved repair real. Returns what changed, for the audit record."""
    with session_scope() as db:
        row, incident = _load(db, tenant_id, remediation_id)
        action, model_id = row.action, row.model_id
        detail: dict = {}

        if action == "quarantine_input":
            detail = {"held": row.params["inputs"]}

        elif action == "release_input":
            released = set(row.params["inputs"])
            for q in db.execute(
                select(Remediation).where(
                    Remediation.incident_id == incident.id,
                    Remediation.action == "quarantine_input",
                    Remediation.status == "applied",
                )
            ).scalars():
                if released.issuperset(q.params.get("inputs", [])):
                    q.status = "released"
            detail = {"released": sorted(released)}

        elif action == "rebaseline":
            model = db.execute(
                select(Model).where(Model.tenant_id == tenant_id, Model.model_id == model_id)
            ).scalar_one()
            row.undo = {"baseline": model.baseline, "baseline_at": iso_utc(model.baseline_at)}
            model.baseline = row.params["baseline"]
            model.baseline_at = datetime.now(UTC)
            detail = {"new_reference_size": row.params.get("window")}

        elif action == "rollback_baseline":
            target = db.get(Remediation, row.params["target"])
            model = db.execute(
                select(Model).where(Model.tenant_id == tenant_id, Model.model_id == model_id)
            ).scalar_one()
            model.baseline = (target.undo or {})["baseline"]
            model.baseline_at = datetime.now(UTC)
            target.status = "rolled_back"
            detail = {"restored_reference_from": target.id}

        elif action == "request_retrain":
            detail = {"requested_for": row.params.get("inputs", [])}

        row.status = "applied"
        row.applied_at = datetime.now(UTC)
        for sibling in db.execute(
            select(Remediation).where(
                Remediation.incident_id == incident.id,
                Remediation.status == "proposed",
                Remediation.id != row.id,
            )
        ).scalars():
            sibling.status = "superseded"

        if action == "release_input":
            still_held = db.execute(
                select(Remediation).where(
                    Remediation.incident_id == incident.id,
                    Remediation.action == "quarantine_input",
                    Remediation.status == "applied",
                )
            ).first()
            if still_held is None:
                incident.status = "resolved"
                incident.resolved_at = datetime.now(UTC)
                detail["incident_resolved"] = True

    if action in ("quarantine_input", "release_input"):
        invalidate_quarantines(tenant_id, model_id)
    if action == "release_input":
        # Re-measure drift on the verified-healthy traffic only, so the drift
        # floor stops holding decisions on the strength of the broken period.
        snapshot = worker.recompute_drift(tenant_id, model_id)
        if snapshot is not None:
            detail["severity_now"] = round(snapshot["severity"], 4)
    if action in ("rebaseline", "rollback_baseline"):
        # No new snapshot yet, deliberately. Nothing has been measured against
        # the new reference, so the last reading stays in force — if it was
        # holding decisions under the drift floor, it keeps holding them until
        # fresh traffic is scored at verification. Erring toward REVIEW.
        detail["drift"] = (
            f"re-measured against the new reference once {worker.MIN_SAMPLES} new requests arrive"
        )
    if action == "rollback_baseline":
        with session_scope() as db:
            incident_id = db.get(Remediation, remediation_id).incident_id
            pending = db.execute(
                select(Remediation).where(
                    Remediation.incident_id == incident_id, Remediation.status == "proposed"
                )
            ).first()
            if pending is None:
                incident = db.get(Incident, incident_id)
                new = _add_proposal(
                    db, incident, _propose_retrain(_diagnose_now(tenant_id, model_id))
                )
        if pending is None:
            with session_scope() as db:
                _record_proposal(db.get(Remediation, new.id))
    return detail


# --- verify ------------------------------------------------------------------


def verify(tenant_id: str, incident_id: int) -> dict:
    with _LOCK:
        return _verify_locked(tenant_id, incident_id)


def _verify_locked(tenant_id: str, incident_id: int) -> dict:
    """Did the applied repair work? Resolve, or propose the next step.

    Records an event only when something changes, so verification can run
    after every recompute without filling the chain with "still the same".
    """
    with session_scope() as db:
        incident = db.get(Incident, incident_id)
        if incident is None or incident.tenant_id != tenant_id:
            raise NotFound(f"incident {incident_id} not found")
        if incident.status != "open":
            return {"incident": get_incident(tenant_id, incident_id), "new": False}
        model_id, kind = incident.model_id, incident.kind
        rows = list(
            db.execute(select(Remediation).where(Remediation.incident_id == incident_id)).scalars()
        )
        applied = {r.action: r for r in rows if r.status == "applied"}
        pending = [r for r in rows if r.status == "proposed"]
        applied_ids = {a: r.id for a, r in applied.items()}

    if {"rebaseline", "rollback_baseline"} & set(applied):
        # The reference changed; re-measure drift against it on the traffic
        # that arrived since, so the gateway's reading reflects the repair.
        worker.recompute_drift(tenant_id, model_id)
    diagnosis = _diagnose_now(tenant_id, model_id)
    outcome = "unchanged"

    if kind == "pipeline_break" and "quarantine_input" in applied:
        held = applied["quarantine_input"].params.get("inputs", [])
        broken = {i.name for i in diagnosis.broken}
        recovered = diagnosis.kind != "insufficient_data" and not (broken & set(held))
        if recovered and not any(p.action == "release_input" for p in pending):
            proposal = _propose_release(tenant_id, model_id, held, diagnosis)
            with session_scope() as db:
                new = _add_proposal(db, db.get(Incident, incident_id), proposal)
            _record(
                tenant_id,
                model_id,
                "verified",
                incident_id,
                remediation_id=applied_ids["quarantine_input"],
                detail={"result": "feed healthy again", "inputs": held},
            )
            with session_scope() as db:
                _record_proposal(db.get(Remediation, new.id))
            outcome = "release_proposed"

    elif kind == "population_shift" and ("rebaseline" in applied or "request_retrain" in applied):
        healthy = diagnosis.kind == "healthy"
        if healthy:
            with session_scope() as db:
                incident = db.get(Incident, incident_id)
                incident.status = "resolved"
                incident.resolved_at = datetime.now(UTC)
            _record(
                tenant_id,
                model_id,
                "verified",
                incident_id,
                detail={"result": "drift back within range", "severity": diagnosis.severity},
            )
            outcome = "resolved"
        elif (
            diagnosis.kind == "population_shift"
            and "rebaseline" in applied
            and not any(p.action == "rollback_baseline" for p in pending)
        ):
            with session_scope() as db:
                target = db.get(Remediation, applied_ids["rebaseline"])
                target.status = "failed_verification"
                proposal = _propose_rollback(tenant_id, model_id, target)
                new = _add_proposal(db, db.get(Incident, incident_id), proposal)
            _record(
                tenant_id,
                model_id,
                "verification_failed",
                incident_id,
                remediation_id=applied_ids["rebaseline"],
                detail={"severity": diagnosis.severity, "band": diagnosis.band},
            )
            with session_scope() as db:
                _record_proposal(db.get(Remediation, new.id))
            outcome = "rollback_proposed"

    return {
        "incident": get_incident(tenant_id, incident_id),
        "new": False,
        "verification": outcome,
        "diagnosis": diagnosis.to_dict(),
    }


# --- views -------------------------------------------------------------------


def _remediation_out(r: Remediation) -> dict:
    params = dict(r.params or {})
    if "baseline" in params:
        # The candidate reference is hundreds of numbers per input; the view
        # needs its size, not its contents.
        params["baseline"] = {name: len(values) for name, values in params["baseline"].items()}
    return {
        "id": r.id,
        "action": r.action,
        "status": r.status,
        "params": params,
        "rationale": r.rationale,
        "shadow": r.shadow,
        "decided_by": r.decided_by,
        "decision_note": r.decision_note,
        "proposed_at": iso_utc(r.proposed_at),
        "decided_at": iso_utc(r.decided_at),
        "applied_at": iso_utc(r.applied_at),
    }


def _incident_out(i: Incident, remediations: list[Remediation]) -> dict:
    return {
        "id": i.id,
        "model_id": i.model_id,
        "kind": i.kind,
        "status": i.status,
        "summary": i.summary,
        "diagnosis": i.diagnosis,
        "opened_at": iso_utc(i.opened_at),
        "resolved_at": iso_utc(i.resolved_at),
        "remediations": [_remediation_out(r) for r in remediations],
    }


def get_incident(tenant_id: str, incident_id: int) -> dict:
    with session_scope() as db:
        incident = db.get(Incident, incident_id)
        if incident is None or incident.tenant_id != tenant_id:
            raise NotFound(f"incident {incident_id} not found")
        rows = list(
            db.execute(
                select(Remediation)
                .where(Remediation.incident_id == incident_id)
                .order_by(Remediation.id)
            ).scalars()
        )
        return _incident_out(incident, rows)


def list_incidents(
    tenant_id: str, status: str | None = None, model_id: str | None = None, limit: int = 50
) -> list[dict]:
    with session_scope() as db:
        stmt = select(Incident).where(Incident.tenant_id == tenant_id)
        if status:
            stmt = stmt.where(Incident.status == status)
        if model_id:
            stmt = stmt.where(Incident.model_id == model_id)
        incidents = list(db.execute(stmt.order_by(Incident.id.desc()).limit(limit)).scalars())
        out = []
        for incident in incidents:
            rows = list(
                db.execute(
                    select(Remediation)
                    .where(Remediation.incident_id == incident.id)
                    .order_by(Remediation.id)
                ).scalars()
            )
            out.append(_incident_out(incident, rows))
        return out
