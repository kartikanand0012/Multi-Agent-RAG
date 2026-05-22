"""Admin-only endpoints — accessible only to kartikanand0012@gmail.com.

All queries use JOINs / subqueries rather than N+1 loops.
Access gated by require_admin (is_admin flag, always mirrored from user_roles).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.db.models import (
    AgentRun, Alert, IngestionJob, Quota, Role, User, UserRole,
)
from app.db.session import get_db

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


# ── Overview (single CTE query) ───────────────────────────────────────────────

@router.get("/overview")
async def overview(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)

    user_count   = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    run_total    = (await db.execute(select(func.count()).select_from(AgentRun))).scalar_one()
    run_today    = (await db.execute(select(func.count()).select_from(AgentRun).where(AgentRun.created_at >= today))).scalar_one()
    run_week     = (await db.execute(select(func.count()).select_from(AgentRun).where(AgentRun.created_at >= week_ago))).scalar_one()
    upload_total = (await db.execute(select(func.count()).select_from(IngestionJob))).scalar_one()
    upload_today = (await db.execute(select(func.count()).select_from(IngestionJob).where(IngestionJob.queued_at >= today))).scalar_one()
    total_cost   = float((await db.execute(select(func.sum(AgentRun.total_cost_usd)))).scalar_one() or 0)
    failed_runs  = (await db.execute(select(func.count()).select_from(AgentRun).where(AgentRun.status == "failed", AgentRun.created_at >= week_ago))).scalar_one()
    open_alerts  = (await db.execute(select(func.count()).select_from(Alert).where(Alert.resolved_at.is_(None)))).scalar_one()

    return {
        "users":   user_count,
        "queries": {"total": run_total, "today": run_today, "this_week": run_week},
        "uploads": {"total": upload_total, "today": upload_today},
        "total_cost_usd": round(total_cost, 4),
        "failed_runs_this_week": failed_runs,
        "open_alerts": open_alerts,
    }


# ── User list (paginated, single subquery per count) ──────────────────────────

@router.get("/users")
async def list_users(
    limit:  int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(
            User.id, User.email, User.username, User.full_name,
            User.is_admin, User.is_active, User.created_at, User.last_login_at,
            select(func.count()).select_from(AgentRun).where(AgentRun.user_id == User.id).scalar_subquery().label("total_queries"),
            select(func.count()).select_from(IngestionJob).where(IngestionJob.user_id == User.id).scalar_subquery().label("total_uploads"),
        )
        .order_by(User.created_at.desc())
        .limit(limit).offset(offset)
    )
    total = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    return {
        "total": total, "limit": limit, "offset": offset,
        "users": [
            {
                "id": u.id, "email": u.email, "username": u.username,
                "is_admin": u.is_admin, "is_active": u.is_active,
                "created_at": u.created_at.isoformat(),
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                "total_queries": u.total_queries,
                "total_uploads": u.total_uploads,
            }
            for u in rows.all()
        ],
    }


# ── Single user detail ────────────────────────────────────────────────────────

@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: str,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    quota = (await db.execute(select(Quota).where(Quota.user_id == user_id, Quota.period == "daily"))).scalar_one_or_none()
    runs  = (await db.execute(select(AgentRun).where(AgentRun.user_id == user_id).order_by(AgentRun.created_at.desc()).limit(50))).scalars().all()
    jobs  = (await db.execute(select(IngestionJob).where(IngestionJob.user_id == user_id).order_by(IngestionJob.queued_at.desc()).limit(20))).scalars().all()

    return {
        "user": {
            "id": user.id, "email": user.email, "username": user.username,
            "is_admin": user.is_admin, "is_active": user.is_active, "roles": user.roles,
            "created_at": user.created_at.isoformat(),
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        },
        "quota": {
            "used_queries": quota.used_queries, "max_queries": quota.max_queries,
            "used_uploads": quota.used_uploads, "max_uploads": quota.max_uploads,
            "resets_at": quota.resets_at.isoformat(),
        } if quota else None,
        "recent_runs": [
            {"id": r.id, "query": r.query_text[:100], "status": r.status.value,
             "validation_passed": r.validation_passed, "latency_ms": r.latency_ms,
             "created_at": r.created_at.isoformat(), "error": r.error or None}
            for r in runs
        ],
        "recent_uploads": [
            {"id": j.id, "file": j.original_filename, "status": j.status.value,
             "nodes": j.total_nodes, "queued_at": j.queued_at.isoformat()}
            for j in jobs
        ],
    }


# ── Runs feed ─────────────────────────────────────────────────────────────────

@router.get("/runs")
async def list_runs(
    failed: bool = Query(False),
    since: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    q = select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit)
    if failed:
        q = q.where(AgentRun.status == "failed")
    if since:
        q = q.where(AgentRun.created_at >= datetime.fromisoformat(since))
    runs = (await db.execute(q)).scalars().all()
    return {"runs": [{"id": r.id, "user_id": r.user_id, "query": r.query_text[:120],
                      "status": r.status.value, "error": r.error or None,
                      "latency_ms": r.latency_ms, "created_at": r.created_at.isoformat()} for r in runs]}


# ── Cost breakdown ────────────────────────────────────────────────────────────

@router.get("/costs")
async def cost_breakdown(
    period: str = Query("monthly", regex="^(daily|monthly|all)$"),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    since = {"daily": now.replace(hour=0, minute=0, second=0, microsecond=0),
             "monthly": now.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
             "all": datetime(2000, 1, 1, tzinfo=timezone.utc)}[period]

    rows = await db.execute(
        select(
            AgentRun.user_id,
            func.count().label("runs"),
            func.sum(AgentRun.total_tokens_in).label("tokens_in"),
            func.sum(AgentRun.total_tokens_out).label("tokens_out"),
            func.sum(AgentRun.total_cost_usd).label("cost"),
        )
        .where(AgentRun.created_at >= since)
        .group_by(AgentRun.user_id)
        .order_by(func.sum(AgentRun.total_cost_usd).desc())
    )
    return {"period": period, "breakdown": [
        {"user_id": r.user_id, "runs": r.runs,
         "tokens_in": r.tokens_in or 0, "tokens_out": r.tokens_out or 0,
         "cost_usd": float(r.cost or 0)}
        for r in rows.all()
    ]}


# ── Alerts ────────────────────────────────────────────────────────────────────

@router.get("/alerts")
async def list_alerts(
    status: str = Query("open", regex="^(open|resolved|all)$"),
    limit: int = Query(50, ge=1, le=200),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    q = select(Alert).order_by(Alert.created_at.desc()).limit(limit)
    if status == "open":
        q = q.where(Alert.resolved_at.is_(None))
    elif status == "resolved":
        q = q.where(Alert.resolved_at.isnot(None))
    alerts = (await db.execute(q)).scalars().all()
    return {"alerts": [{"id": a.id, "severity": a.severity.value, "source": a.source,
                         "title": a.title, "body": a.body,
                         "created_at": a.created_at.isoformat(),
                         "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None} for a in alerts]}


@router.post("/alerts/{alert_id}/resolve", status_code=204)
async def resolve_alert(alert_id: str, _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    alert = (await db.execute(select(Alert).where(Alert.id == alert_id))).scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.resolved_at = datetime.now(timezone.utc)


# ── Quota management ──────────────────────────────────────────────────────────

@router.patch("/users/{user_id}/quota")
async def update_quota(
    user_id: str,
    max_queries: Optional[int] = None,
    max_uploads: Optional[int] = None,
    max_tokens:  Optional[int] = None,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    quota = (await db.execute(select(Quota).where(Quota.user_id == user_id, Quota.period == "daily"))).scalar_one_or_none()
    if not quota:
        raise HTTPException(status_code=404, detail="Quota not found")
    if max_queries is not None: quota.max_queries = max_queries
    if max_uploads is not None: quota.max_uploads = max_uploads
    if max_tokens  is not None: quota.max_tokens  = max_tokens
    return {"user_id": user_id, "max_queries": quota.max_queries,
            "max_uploads": quota.max_uploads, "max_tokens": quota.max_tokens}


# ── Role management ───────────────────────────────────────────────────────────

@router.post("/users/{user_id}/roles/{role_name}", status_code=204)
async def grant_role(
    user_id: str, role_name: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    role = (await db.execute(select(Role).where(Role.name == role_name))).scalar_one_or_none()
    if not user: raise HTTPException(status_code=404, detail="User not found")
    if not role: raise HTTPException(status_code=404, detail=f"Role '{role_name}' not found")

    exists = (await db.execute(select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role.id))).scalar_one_or_none()
    if not exists:
        db.add(UserRole(user_id=user_id, role_id=role.id, granted_by=admin.id))
    if role_name == "admin":
        user.is_admin = True


@router.delete("/users/{user_id}/roles/{role_name}", status_code=204)
async def revoke_role(
    user_id: str, role_name: str,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    role = (await db.execute(select(Role).where(Role.name == role_name))).scalar_one_or_none()
    if not role: raise HTTPException(status_code=404, detail=f"Role '{role_name}' not found")

    ur = (await db.execute(select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role.id))).scalar_one_or_none()
    if ur:
        await db.delete(ur)
    if role_name == "admin":
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if user: user.is_admin = False
