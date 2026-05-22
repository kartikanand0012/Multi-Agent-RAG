"""Upload endpoint — returns 202 + job_id; Celery runs RAPTOR in background."""
from __future__ import annotations

import tempfile
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.models import IngestionJob, JobStatus, Notebook, User
from app.db.session import get_db
from app.middleware.quota import check_upload_quota, increment_upload_quota

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["ingestion"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xls", ".txt", ".md", ".htm", ".html"}


async def _get_or_create_notebook(notebook_id: str, user: User, db: AsyncSession, name: str | None = None) -> Notebook:
    result = await db.execute(select(Notebook).where(Notebook.id == notebook_id))
    nb = result.scalar_one_or_none()
    if nb:
        if nb.user_id != user.id:
            raise HTTPException(status_code=403, detail="Access denied to this notebook")
        return nb
    nb = Notebook(
        id=notebook_id,
        name=name or notebook_id.replace("-", " ").title(),
        user_id=user.id,
    )
    db.add(nb)
    await db.flush()
    return nb


@router.post("/upload", status_code=202, tags=["ingestion"])
async def upload(
    file:         UploadFile = File(...),
    notebook_id:  str        = Form(default="default"),
    use_raptor:   bool       = Form(default=True),
    current_user: User       = Depends(get_current_user),
    db: AsyncSession         = Depends(get_db),
):
    """Accept a document, create an IngestionJob, queue with Celery.

    Returns 202 Accepted immediately. Poll GET /ingestion/{job_id} for status.
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{suffix}'.")

    await check_upload_quota(current_user, db)

    nb = await _get_or_create_notebook(notebook_id, current_user, db)

    # Write to a deterministic temp path so the Celery worker can read it
    content = await file.read()
    job_id_placeholder = None  # we'll get it after flush

    job = IngestionJob(
        user_id=current_user.id,
        notebook_id=nb.id,
        original_filename=file.filename or "unknown",
        file_size_bytes=len(content),
        use_raptor=use_raptor,
        status=JobStatus.queued,
    )
    db.add(job)
    await db.flush()

    # Write bytes to deterministic path keyed on job.id
    tmp_path = Path(tempfile.gettempdir()) / f"ingest_{job.id}"
    tmp_path.write_bytes(content)

    await increment_upload_quota(current_user, db)

    # Queue Celery task
    try:
        from app.workers.tasks import ingest_document
        task = ingest_document.delay(job.id)
        job.celery_task_id = task.id
        logger.info("Ingestion queued", job_id=job.id, file=file.filename, task_id=task.id)
    except Exception as e:
        logger.error("Celery unavailable — falling back to inline ingestion", error=str(e))
        # Inline fallback so uploads still work without a worker
        from app.ingestion.pipeline import ingest_file
        import time as _time
        t0 = _time.monotonic()
        job.status = JobStatus.processing
        try:
            result = await ingest_file(tmp_path, notebook_id=nb.id, use_raptor=use_raptor)
            job.status      = JobStatus.done
            job.total_nodes = result["total_nodes"]
            job.leaf_chunks = result["leaf_chunks"]
            job.processing_ms = int((_time.monotonic() - t0) * 1000)
            nb.doc_count    += 1
            nb.total_chunks += result["leaf_chunks"]
        except Exception as exc:
            job.status = JobStatus.failed
            job.error  = str(exc)[:500]
        finally:
            tmp_path.unlink(missing_ok=True)

    return {
        "job_id": job.id,
        "status": job.status.value,
        "file": file.filename,
        "notebook_id": nb.id,
        "status_url": f"/api/v1/ingestion/{job.id}",
    }


@router.get("/ingestion/{job_id}", tags=["ingestion"])
async def get_ingestion_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession   = Depends(get_db),
):
    """Poll job status. Frontend polls until status == 'done' or 'failed'."""
    result = await db.execute(select(IngestionJob).where(IngestionJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job or job.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Ingestion job not found")

    return {
        "job_id":         job.id,
        "status":         job.status.value,
        "file":           job.original_filename,
        "notebook_id":    job.notebook_id,
        "total_nodes":    job.total_nodes,
        "leaf_chunks":    job.leaf_chunks,
        "processing_ms":  job.processing_ms,
        "error":          job.error or None,
        "queued_at":      job.queued_at.isoformat(),
        "started_at":     job.started_at.isoformat() if job.started_at else None,
        "finished_at":    job.finished_at.isoformat() if job.finished_at else None,
    }
