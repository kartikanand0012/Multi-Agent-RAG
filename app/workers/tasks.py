"""Celery tasks.

ingest_document  — runs RAPTOR pipeline in background; updates IngestionJob row.
record_usage     — durable replacement for the old fire-and-forget _log_query.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    return asyncio.get_event_loop().run_until_complete(coro)


@celery_app.task(
    bind=True,
    name="app.workers.tasks.ingest_document",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def ingest_document(self, job_id: str) -> dict:
    """Runs the full ingestion pipeline for one IngestionJob row.

    Handles its own DB session so it's isolated from the web worker.
    """
    return _run_async(_ingest_document_async(self, job_id))


async def _ingest_document_async(task, job_id: str) -> dict:
    from pathlib import Path
    import tempfile

    from sqlalchemy import select

    from app.core.alerts import send_alert
    from app.db.base import AsyncSessionLocal
    from app.db.models import IngestionJob, JobStatus, Notebook
    from app.ingestion.pipeline import ingest_file

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(IngestionJob).where(IngestionJob.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            logger.error("ingest_document: job %s not found", job_id)
            return {"error": "not found"}

        job.status = JobStatus.processing
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

        t0 = time.monotonic()
        try:
            # The file bytes were written to a temp path before queueing;
            # the path is stored in job metadata (see routes_upload.py).
            # We re-create a NamedTemporaryFile from the stored bytes for now.
            # Phase 3: swap for S3/R2 object store.
            tmp_path = Path(tempfile.gettempdir()) / f"ingest_{job_id}"
            if not tmp_path.exists():
                raise FileNotFoundError(f"Temp file for job {job_id} missing — did worker restart?")

            suffix = Path(job.original_filename).suffix.lower()
            output = await ingest_file(
                tmp_path,
                notebook_id=job.notebook_id,
                use_raptor=job.use_raptor,
                display_name=job.original_filename,
            )

            job.status      = JobStatus.done
            job.finished_at = datetime.now(timezone.utc)
            job.processing_ms = int((time.monotonic() - t0) * 1000)
            job.total_nodes  = output["total_nodes"]
            job.leaf_chunks  = output["leaf_chunks"]

            # Update notebook doc count
            nb_result = await db.execute(select(Notebook).where(Notebook.id == job.notebook_id))
            nb = nb_result.scalar_one_or_none()
            if nb:
                nb.doc_count    += 1
                nb.total_chunks += output["leaf_chunks"]

            await db.commit()
            logger.info("Ingestion job %s done: %d nodes in %dms", job_id, output["total_nodes"], job.processing_ms)
            return {"job_id": job_id, "status": "done", "total_nodes": output["total_nodes"]}

        except Exception as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            logger.error("Ingestion job %s failed: %s", job_id, exc)
            job.status      = JobStatus.failed
            job.finished_at = datetime.now(timezone.utc)
            job.processing_ms = elapsed
            job.error       = str(exc)[:500]
            await db.commit()

            await send_alert(
                severity="error",
                source="celery.ingest",
                title=f"Ingestion failed: {job.original_filename}",
                body=f"Job {job_id}\n{exc}",
            )

            # Retry on transient errors; don't retry on FileNotFoundError (file is gone)
            if not isinstance(exc, FileNotFoundError):
                raise task.retry(exc=exc)

            return {"job_id": job_id, "status": "failed", "error": str(exc)}

        finally:
            # Clean up temp file
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass


@celery_app.task(
    name="app.workers.tasks.record_usage",
    max_retries=5,
    default_retry_delay=10,
    acks_late=True,
)
def record_usage(
    user_id: str,
    event_type: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_usd: float = 0.0,
    agent_run_id: str | None = None,
    ingestion_job_id: str | None = None,
) -> None:
    """Persist a UsageEvent row. Durable replacement for fire-and-forget analytics."""
    _run_async(_record_usage_async(
        user_id=user_id, event_type=event_type,
        tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost_usd,
        agent_run_id=agent_run_id, ingestion_job_id=ingestion_job_id,
    ))


async def _record_usage_async(**kwargs) -> None:
    from decimal import Decimal
    from app.db.base import AsyncSessionLocal
    from app.db.models import UsageEvent, UsageEventType

    async with AsyncSessionLocal() as db:
        event = UsageEvent(
            user_id=kwargs["user_id"],
            event_type=UsageEventType(kwargs["event_type"]),
            tokens_in=kwargs.get("tokens_in", 0),
            tokens_out=kwargs.get("tokens_out", 0),
            cost_usd=Decimal(str(kwargs.get("cost_usd", 0))),
            agent_run_id=kwargs.get("agent_run_id"),
            ingestion_job_id=kwargs.get("ingestion_job_id"),
        )
        db.add(event)
        await db.commit()
