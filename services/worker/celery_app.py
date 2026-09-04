"""Celery app; registers drift worker tasks + audit writer.

Optional infrastructure. Every task here is a thin wrapper over a plain function
in ``engines/drift/worker.py``, so the drift pipeline runs identically with or
without a broker — Celery adds scheduling and retries, not behaviour.
"""

from __future__ import annotations

import os

from celery import Celery

from shared.db.session import init_engine

BROKER_URL = os.getenv("CUSTOS_REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("custos", broker=BROKER_URL, backend=BROKER_URL)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Drift work is idempotent — recomputing a window twice yields the same
    # snapshot — so late acknowledgement is safe and a worker dying mid-task
    # costs a rerun rather than a silently skipped window.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# Ensures @shared_task-decorated tasks in engines/drift/worker.py register.
celery_app.autodiscover_tasks(["engines.drift"])


@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **_kwargs) -> None:
    """Recompute drift for every model on a fixed cadence.

    Hourly is a deliberate default: PSI over a window shorter than that is
    dominated by intraday traffic patterns rather than genuine distribution
    change, so a faster cadence would buy noise, not sensitivity.
    """
    sender.add_periodic_task(3600.0, recompute_all_models.s(), name="hourly drift recompute")


@celery_app.task(name="custos.recompute_all_models")
def recompute_all_models() -> dict:
    """Fan out a recompute across every model that has a baseline."""
    from sqlalchemy import select

    from engines.drift.worker import recompute_drift
    from shared.db.models import Model
    from shared.db.session import session_scope

    init_engine()
    computed, skipped = 0, 0

    with session_scope() as db:
        targets = [
            (m.tenant_id, m.model_id)
            for m in db.execute(select(Model).where(Model.baseline.is_not(None))).scalars()
        ]

    for tenant_id, model_id in targets:
        try:
            result = recompute_drift(tenant_id, model_id)
        except Exception:
            skipped += 1
            continue
        computed += 1 if result else 0
        skipped += 0 if result else 1

    return {"models": len(targets), "computed": computed, "skipped": skipped}
