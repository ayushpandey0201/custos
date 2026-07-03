"""Celery app; registers drift worker tasks + audit writer."""

from celery import Celery

celery_app = Celery("custos")

# Ensures @shared_task-decorated tasks in engines/drift/worker.py register.
celery_app.autodiscover_tasks(["engines.drift"])

