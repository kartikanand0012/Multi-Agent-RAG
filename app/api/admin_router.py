"""Admin-only analytics endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.db.models import Notebook, QueryEvent, UploadEvent, User
from app.db.session import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


class OverviewStats(BaseModel):
    total_users:       int
    total_notebooks:   int
    total_queries:     int
    total_uploads:     int
    queries_today:     int
    uploads_today:     int
    queries_this_week: int


class UserRow(BaseModel):
    id:            str
    email:         str
    username:      str
    total_queries: int
    total_uploads: int
    last_login_at: datetime | None
    created_at:    datetime

    model_config = {"from_attributes": True}


@router.get("/stats/overview", response_model=OverviewStats)
async def overview(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    now  = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week  = today - timedelta(days=7)

    total_users     = (await db.execute(select(func.count(User.id)))).scalar_one()
    total_notebooks = (await db.execute(select(func.count(Notebook.id)))).scalar_one()
    total_queries   = (await db.execute(select(func.count(QueryEvent.id)))).scalar_one()
    total_uploads   = (await db.execute(select(func.count(UploadEvent.id)))).scalar_one()
    queries_today   = (await db.execute(select(func.count(QueryEvent.id)).where(QueryEvent.created_at >= today))).scalar_one()
    uploads_today   = (await db.execute(select(func.count(UploadEvent.id)).where(UploadEvent.created_at >= today))).scalar_one()
    queries_week    = (await db.execute(select(func.count(QueryEvent.id)).where(QueryEvent.created_at >= week))).scalar_one()

    return OverviewStats(
        total_users=total_users,
        total_notebooks=total_notebooks,
        total_queries=total_queries,
        total_uploads=total_uploads,
        queries_today=queries_today,
        uploads_today=uploads_today,
        queries_this_week=queries_week,
    )


@router.get("/stats/users")
async def users_list(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    users = (await db.execute(select(User).order_by(User.created_at.desc()))).scalars().all()
    rows = []
    for u in users:
        q = (await db.execute(select(func.count(QueryEvent.id)).where(QueryEvent.user_id == u.id))).scalar_one()
        up = (await db.execute(select(func.count(UploadEvent.id)).where(UploadEvent.user_id == u.id))).scalar_one()
        rows.append({
            "id": u.id, "email": u.email, "username": u.username,
            "total_queries": q, "total_uploads": up,
            "last_login_at": u.last_login_at, "created_at": u.created_at,
        })
    return rows


@router.get("/stats/user/{user_id}")
async def user_detail(user_id: str, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        from fastapi import HTTPException
        raise HTTPException(404, "User not found")

    queries = (await db.execute(
        select(QueryEvent).where(QueryEvent.user_id == user_id)
        .order_by(QueryEvent.created_at.desc()).limit(50)
    )).scalars().all()

    uploads = (await db.execute(
        select(UploadEvent).where(UploadEvent.user_id == user_id)
        .order_by(UploadEvent.created_at.desc()).limit(20)
    )).scalars().all()

    return {
        "user": {"id": user.id, "email": user.email, "username": user.username, "created_at": user.created_at},
        "recent_queries": [
            {"id": q.id, "notebook_id": q.notebook_id, "intent_type": q.intent_type,
             "sources_found": q.sources_found, "latency_ms": q.latency_ms, "created_at": q.created_at}
            for q in queries
        ],
        "recent_uploads": [
            {"id": u.id, "filename": u.original_filename, "total_nodes": u.total_nodes,
             "processing_ms": u.processing_ms, "created_at": u.created_at}
            for u in uploads
        ],
    }
