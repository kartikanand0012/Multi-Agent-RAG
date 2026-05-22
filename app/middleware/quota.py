"""Per-user quota enforcement.

Checked before query and upload endpoints. Creates the default daily quota row
on first encounter. Returns 429 with Retry-After when limits are exceeded.

Usage (in a route):
    from app.middleware.quota import check_query_quota, increment_query_quota
    await check_query_quota(current_user, db)   # raises 429 if over limit
    # ... do the query ...
    await increment_query_quota(current_user, db)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Quota, QuotaPeriod, User

logger = logging.getLogger(__name__)

_TOO_MANY = status.HTTP_429_TOO_MANY_REQUESTS


def _start_of_tomorrow() -> datetime:
    now = datetime.now(timezone.utc)
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


async def _get_or_create_quota(user: User, db: AsyncSession) -> Quota:
    result = await db.execute(
        select(Quota).where(Quota.user_id == user.id, Quota.period == QuotaPeriod.daily)
    )
    quota = result.scalar_one_or_none()
    if not quota:
        quota = Quota(
            user_id=user.id,
            period=QuotaPeriod.daily,
            max_queries=settings.quota_max_queries_daily,
            max_uploads=settings.quota_max_uploads_daily,
            max_tokens=settings.quota_max_tokens_daily,
            resets_at=_start_of_tomorrow(),
        )
        db.add(quota)
        await db.flush()
    elif quota.resets_at and quota.resets_at <= datetime.now(timezone.utc):
        # Reset expired window
        quota.used_queries = 0
        quota.used_uploads = 0
        quota.used_tokens  = 0
        quota.resets_at    = _start_of_tomorrow()
    return quota


async def check_query_quota(user: User, db: AsyncSession) -> None:
    if user.is_admin:
        return  # admins are exempt
    quota = await _get_or_create_quota(user, db)
    if quota.used_queries >= quota.max_queries:
        resets_in = max(0, int((quota.resets_at - datetime.now(timezone.utc)).total_seconds()))
        raise HTTPException(
            status_code=_TOO_MANY,
            detail=f"Daily query limit ({quota.max_queries}) reached.",
            headers={"Retry-After": str(resets_in)},
        )


async def check_upload_quota(user: User, db: AsyncSession) -> None:
    if user.is_admin:
        return
    quota = await _get_or_create_quota(user, db)
    if quota.used_uploads >= quota.max_uploads:
        resets_in = max(0, int((quota.resets_at - datetime.now(timezone.utc)).total_seconds()))
        raise HTTPException(
            status_code=_TOO_MANY,
            detail=f"Daily upload limit ({quota.max_uploads}) reached.",
            headers={"Retry-After": str(resets_in)},
        )


async def increment_query_quota(user: User, db: AsyncSession) -> None:
    if user.is_admin:
        return
    result = await db.execute(
        select(Quota).where(Quota.user_id == user.id, Quota.period == QuotaPeriod.daily)
    )
    quota = result.scalar_one_or_none()
    if quota:
        quota.used_queries += 1


async def increment_upload_quota(user: User, db: AsyncSession) -> None:
    if user.is_admin:
        return
    result = await db.execute(
        select(Quota).where(Quota.user_id == user.id, Quota.period == QuotaPeriod.daily)
    )
    quota = result.scalar_one_or_none()
    if quota:
        quota.used_uploads += 1
