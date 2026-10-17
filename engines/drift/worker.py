"""Celery tasks: recompute_drift() and build_baseline().

All the expensive statistics live here, off the hot path (ADR 0002).

The logic is written as plain functions and the Celery tasks are thin wrappers
around them. That keeps the drift pipeline directly callable — from tests, from
the demo, from a REPL — without a broker running, and means Celery is an
optional dependency rather than a prerequisite for the system to work.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from engines.drift import engine as drift_engine
from engines.drift.detectors import ks_test, psi
from engines.drift.severity import compute_severity, feature_severity
from shared.config import defaults
from shared.db.models import DriftSnapshot, FeatureSample, Model
from shared.db.session import session_scope
from shared.telemetry.logging import get_logger

log = get_logger(__name__)

# A PSI over a handful of observations is noise. Below this the window is not
# scored at all — reported as degraded rather than as a confident severity.
MIN_SAMPLES = 30
DEFAULT_WINDOW_HOURS = 24


def build_baseline(
    tenant_id: str, model_id: str, samples: list[dict[str, float]] | None = None
) -> dict[str, list[float]]:
    """Capture a model's reference distribution.

    Drift is always measured against this fixed baseline, never against the
    previous window. Comparing consecutive windows makes slow drift invisible —
    each window looks like the one before it while the model walks steadily away
    from what it was trained on.

    Args:
        samples: observations to use. When omitted, every stored sample for the
            model is used, which is the normal path right after a backfill.

    Returns:
        ``{feature_name: [values...]}`` as persisted.

    Raises:
        LookupError: if the model is not registered.
        ValueError: if there are no samples to build from.
    """
    with session_scope() as db:
        model = db.execute(
            select(Model).where(Model.tenant_id == tenant_id, Model.model_id == model_id)
        ).scalar_one_or_none()
        if model is None:
            raise LookupError(f"model {model_id!r} is not registered for tenant {tenant_id!r}")

        rows = samples
        if rows is None:
            rows = [
                r.features
                for r in db.execute(
                    select(FeatureSample).where(
                        FeatureSample.tenant_id == tenant_id,
                        FeatureSample.model_id == model_id,
                    )
                ).scalars()
            ]
        if not rows:
            raise ValueError(f"no samples available to build a baseline for {model_id!r}")

        baseline = _columnar(rows)
        model.baseline = baseline
        model.baseline_at = datetime.now(UTC)

    log.info(
        "baseline_built",
        extra={"tenant_id": tenant_id, "model_id": model_id, "features": len(baseline)},
    )
    return baseline


def recompute_drift(
    tenant_id: str,
    model_id: str,
    window_hours: int = DEFAULT_WINDOW_HOURS,
    latest: int | None = None,
) -> dict | None:
    """Score the recent live window against the baseline and persist a snapshot.

    Args:
        latest: score only the most recent ``latest`` samples inside the
            window. Used after a self-healing repair, where the question is
            what traffic looks like *now*, not averaged over the whole day.

    Returns the snapshot dict, or None when there is nothing to score (no
    baseline, or too few samples). Returning None rather than a zero-severity
    snapshot is what lets the hot path stay degraded instead of reading an
    absence of data as an absence of drift.
    """
    with session_scope() as db:
        model = db.execute(
            select(Model).where(Model.tenant_id == tenant_id, Model.model_id == model_id)
        ).scalar_one_or_none()
        if model is None or not model.baseline:
            log.info("drift_skipped", extra={"model_id": model_id, "reason": "no_baseline"})
            return None

        since = datetime.now(UTC) - timedelta(hours=window_hours)
        # Traffic from before the current baseline was set is not live traffic
        # against it. Without this, the baseline's own rows (stored as samples
        # when it is supplied) were scored as live traffic and diluted every
        # reading, and after a re-baseline the old population would be scored
        # against the new reference.
        for floor in (model.baseline_at, _repaired_since(db, tenant_id, model_id)):
            if floor is not None:
                since = max(since, floor if floor.tzinfo else floor.replace(tzinfo=UTC))
        stmt = select(FeatureSample).where(
            FeatureSample.tenant_id == tenant_id,
            FeatureSample.model_id == model_id,
            FeatureSample.created_at >= since,
        )
        if latest is not None:
            stmt = stmt.order_by(FeatureSample.id.desc()).limit(latest)
        live_rows = [r.features for r in db.execute(stmt).scalars()]

        if len(live_rows) < MIN_SAMPLES:
            log.info(
                "drift_skipped",
                extra={"model_id": model_id, "reason": "insufficient_samples", "n": len(live_rows)},
            )
            return None

        live = _columnar(live_rows)
        per_feature = score_features(model.baseline, live)

        if not per_feature:
            log.info("drift_skipped", extra={"model_id": model_id, "reason": "no_common_features"})
            return None

        severity = compute_severity({n: s["severity"] for n, s in per_feature.items()})
        snapshot = DriftSnapshot(
            tenant_id=tenant_id,
            model_id=model_id,
            severity=severity,
            per_feature=per_feature,
            sample_size=len(live_rows),
        )
        db.add(snapshot)

    # Evict so the gateway sees the new severity immediately rather than
    # serving a stale one for the rest of the TTL.
    drift_engine.invalidate(tenant_id, model_id)

    log.info(
        "drift_recomputed",
        extra={
            "tenant_id": tenant_id,
            "model_id": model_id,
            "severity": round(severity, 4),
            "sample_size": len(live_rows),
        },
    )
    return {"severity": severity, "per_feature": per_feature, "sample_size": len(live_rows)}


def _repaired_since(db, tenant_id: str, model_id: str) -> datetime | None:
    """Start of the verified-healthy traffic after the latest repaired feed.

    Requests scored while an input feed was broken are not evidence about the
    population — they are garbage that happened to be recorded. Once a person
    has approved releasing a quarantine (services/healing), drift is measured
    from the first request of the window that verified the repair. Without
    this the drift floor would keep holding decisions for a day after the
    feed was fixed, on the strength of data everyone agrees was broken.
    """
    from shared.db.models import Remediation

    rows = db.execute(
        select(Remediation.params).where(
            Remediation.tenant_id == tenant_id,
            Remediation.model_id == model_id,
            Remediation.action == "release_input",
            Remediation.status == "applied",
        )
    ).scalars()
    stamps = [datetime.fromisoformat(p["healthy_since"]) for p in rows if p.get("healthy_since")]
    return max(stamps, default=None)


def score_features(
    baseline: dict[str, list[float]], live: dict[str, list[float]]
) -> dict[str, dict]:
    """PSI, KS and severity for every feature present in both distributions.

    A feature that disappeared from live traffic is skipped here and surfaced
    separately — that is a pipeline failure, not distribution drift, and the two
    call for different responses (docs/conversations/01).
    """
    scored: dict[str, dict] = {}
    for name, reference in baseline.items():
        observed = live.get(name)
        if not observed or not reference:
            continue
        try:
            psi_value = psi(reference, observed, buckets=defaults.DRIFT_BUCKETS)
            ks_value = ks_test(reference, observed)
        except ValueError:
            continue
        scored[name] = {
            "psi": round(psi_value, 6),
            "ks": round(ks_value, 6),
            "severity": round(feature_severity(psi_value, ks_value), 6),
        }
    return scored


def _columnar(rows: list[dict]) -> dict[str, list[float]]:
    """Row-oriented samples -> column-oriented feature vectors, numerics only."""
    columns: dict[str, list[float]] = {}
    for row in rows:
        for name, value in (row or {}).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            columns.setdefault(name, []).append(float(value))
    return columns


def missing_features(baseline: dict[str, list[float]], live: dict[str, list[float]]) -> list[str]:
    """Baseline features absent from the live window — a pipeline-health signal."""
    return sorted(set(baseline) - set(live))


# --- Celery registration ---------------------------------------------------
# Optional: without a broker installed the functions above remain fully usable,
# which is how the tests and the demo drive the drift pipeline.

try:
    from celery import shared_task
except ImportError:  # pragma: no cover - exercised only without Celery installed
    pass
else:

    @shared_task(name="custos.recompute_drift")
    def recompute_drift_task(tenant_id: str, model_id: str, window_hours: int = 24) -> dict | None:
        result = recompute_drift(tenant_id, model_id, window_hours)
        # Detection runs on the same schedule as drift (services/healing).
        # Imported here: engines must not depend on services at import time.
        from services.healing import service

        try:
            service.scan(tenant_id, model_id)
        except Exception as exc:
            log.error("healing_scan_failed", extra={"model_id": model_id, "error": str(exc)})
        return result

    @shared_task(name="custos.build_baseline")
    def build_baseline_task(tenant_id: str, model_id: str) -> int:
        return len(build_baseline(tenant_id, model_id))
