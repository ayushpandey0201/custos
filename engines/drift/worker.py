"""Celery tasks: recompute_drift() and build_baseline()."""

from celery import shared_task


@shared_task
def recompute_drift(model_id: str) -> None:
    raise NotImplementedError


@shared_task
def build_baseline(model_id: str) -> None:
    raise NotImplementedError

