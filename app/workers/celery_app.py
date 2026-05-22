"""Celery application factory.

Workers are launched by Dockerfile.worker:
    celery -A app.workers.celery_app worker --loglevel=info --concurrency=4

task_acks_late=True: task is acked only after completion — if worker crashes
mid-task the job is re-queued rather than silently lost.
worker_prefetch_multiplier=1: each worker fetches one task at a time so long
ingestion jobs don't starve short jobs in the same queue.
"""
from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "rag_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_routes={
        "app.workers.tasks.ingest_document": {"queue": "ingestion"},
        "app.workers.tasks.record_usage":    {"queue": "analytics"},
    },
)

# Auto-discover tasks in app.workers.tasks
celery_app.autodiscover_tasks(["app.workers"])
