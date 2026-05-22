"""Authentication endpoints."""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.jwt import create_access_token, create_refresh_token, decode_token
from app.auth.password import hash_password, verify_password
from app.auth.schemas import (
    AccessTokenResponse, ApiKeyCreate, ApiKeyCreated, ApiKeyOut,
    ChangePasswordRequest, LoginRequest, RegisterRequest,
    TokenResponse, UpdateProfileRequest, UserMeResponse, UserProfile, UserStats,
)
from app.cache.token_blacklist import token_blacklist
from app.core.config import settings
from app.db.models import AgentRun, ApiKey, IngestionJob, Notebook, Quota, QuotaPeriod, User
from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _key_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ── Register ───────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(User).where((User.email == body.email) | (User.username == body.username))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email or username already in use")

    is_admin = body.email.lower() == settings.admin_email.lower()
    user = User(
        email=body.email,
        username=body.username,
        hashed_password=hash_password(body.password),
        full_name=body.full_name or body.username,
        is_admin=is_admin,
    )
    db.add(user)
    await db.flush()

    # Auto-create daily quota
    db.add(Quota(
        user_id=user.id, period=QuotaPeriod.daily,
        max_queries=settings.quota_max_queries_daily,
        max_uploads=settings.quota_max_uploads_daily,
        max_tokens=settings.quota_max_tokens_daily,
    ))

    access  = create_access_token(user.id, user.email, roles=["admin"] if is_admin else ["user"])
    refresh, _ = create_refresh_token(user.id)
    # Revoke by jti if user ever calls /auth/logout; no action needed at creation

    logger.info("New user registered: %s", user.email)
    return TokenResponse(access_token=access, refresh_token=refresh)


# ── Login ──────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    user.last_login_at = datetime.now(timezone.utc)

    access  = create_access_token(user.id, user.email, roles=user.roles)
    refresh, _ = create_refresh_token(user.id)

    logger.info("User logged in: %s", user.email)
    return TokenResponse(access_token=access, refresh_token=refresh)


# ── Logout (blacklist refresh token) ──────────────────────────────────────────

@router.post("/logout", status_code=204)
async def logout(refresh_token: str):
    try:
        payload = decode_token(refresh_token)
        jti = payload.get("jti")
        if jti:
            token_blacklist.revoke(jti)
    except JWTError:
        pass  # already expired — nothing to revoke


# ── Refresh ────────────────────────────────────────────────────────────────────

@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(refresh_token: str, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(refresh_token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")

    jti = payload.get("jti", "")
    if jti and token_blacklist.is_revoked(jti):
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")

    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")

    access = create_access_token(user.id, user.email, roles=user.roles)
    return AccessTokenResponse(access_token=access)


# ── Me ─────────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserMeResponse)
async def me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    month_start = datetime(date.today().year, date.today().month, 1, tzinfo=timezone.utc)

    total_q = (await db.execute(
        select(func.count()).select_from(AgentRun).where(AgentRun.user_id == current_user.id)
    )).scalar_one()

    total_u = (await db.execute(
        select(func.count()).select_from(IngestionJob).where(IngestionJob.user_id == current_user.id)
    )).scalar_one()

    nb_count = (await db.execute(
        select(func.count()).select_from(Notebook).where(Notebook.user_id == current_user.id)
    )).scalar_one()

    month_q = (await db.execute(
        select(func.count()).select_from(AgentRun).where(
            AgentRun.user_id == current_user.id,
            AgentRun.created_at >= month_start,
        )
    )).scalar_one()

    month_u = (await db.execute(
        select(func.count()).select_from(IngestionJob).where(
            IngestionJob.user_id == current_user.id,
            IngestionJob.queued_at >= month_start,   # IngestionJob uses queued_at, not created_at
        )
    )).scalar_one()

    return UserMeResponse(
        profile=UserProfile.model_validate(current_user),
        stats=UserStats(
            total_queries=total_q,
            total_uploads=total_u,
            notebooks_count=nb_count,
            queries_this_month=month_q,
            uploads_this_month=month_u,
        ),
    )


# ── Update profile ─────────────────────────────────────────────────────────────

@router.patch("/me", response_model=UserProfile)
async def update_me(
    body: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.username and body.username != current_user.username:
        clash = (await db.execute(select(User).where(User.username == body.username))).scalar_one_or_none()
        if clash:
            raise HTTPException(status_code=409, detail="Username already taken")
        current_user.username = body.username

    if body.full_name is not None:
        current_user.full_name = body.full_name

    return UserProfile.model_validate(current_user)


# ── Change password ────────────────────────────────────────────────────────────

@router.post("/me/change-password", status_code=204)
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
):
    if not verify_password(body.old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Old password is incorrect")
    current_user.hashed_password = hash_password(body.new_password)


# ── API key management ─────────────────────────────────────────────────────────

@router.post("/me/api-keys", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    raw_key = secrets.token_hex(32)   # 64-char hex; shown once
    row = ApiKey(
        user_id=current_user.id,
        key_hash=_key_hash(raw_key),
        label=body.label,
    )
    db.add(row)
    await db.flush()
    return ApiKeyCreated(
        id=row.id, label=row.label,
        last_used_at=row.last_used_at, expires_at=row.expires_at,
        created_at=row.created_at, key=raw_key,
    )


@router.get("/me/api-keys", response_model=list[ApiKeyOut])
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.user_id == current_user.id, ApiKey.revoked_at.is_(None))
        .order_by(ApiKey.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/me/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == current_user.id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="API key not found")
    row.revoked_at = datetime.now(timezone.utc)
