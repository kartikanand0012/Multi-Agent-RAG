"""Authentication endpoints."""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.jwt import create_access_token, create_refresh_token, decode_token
from app.auth.password import hash_password, verify_password
from app.auth.schemas import (
    AccessTokenResponse, ChangePasswordRequest, LoginRequest,
    RegisterRequest, TokenResponse, UpdateProfileRequest,
    UserMeResponse, UserProfile, UserStats,
)
from app.db.models import Notebook, QueryEvent, UploadEvent, User
from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


# ── Register ───────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check uniqueness
    existing = await db.execute(
        select(User).where((User.email == body.email) | (User.username == body.username))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email or username already in use")

    user = User(
        email=body.email,
        username=body.username,
        hashed_password=hash_password(body.password),
        full_name=body.full_name or body.username,
    )
    db.add(user)
    await db.flush()  # get user.id before commit

    access  = create_access_token(user.id, user.email)
    refresh, _ = create_refresh_token(user.id)

    logger.info(f"New user registered: {user.email} ({user.id})")
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

    access  = create_access_token(user.id, user.email)
    refresh, _ = create_refresh_token(user.id)

    logger.info(f"User logged in: {user.email}")
    return TokenResponse(access_token=access, refresh_token=refresh)


# ── Refresh ────────────────────────────────────────────────────────────────────

@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(refresh_token: str, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(refresh_token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")

    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")

    access = create_access_token(user.id, user.email)
    return AccessTokenResponse(access_token=access)


# ── Me ─────────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserMeResponse)
async def me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from datetime import date

    month_start = datetime(date.today().year, date.today().month, 1, tzinfo=timezone.utc)

    total_q = (await db.execute(
        select(func.count()).where(QueryEvent.user_id == current_user.id)
    )).scalar_one()

    total_u = (await db.execute(
        select(func.count()).where(UploadEvent.user_id == current_user.id)
    )).scalar_one()

    nb_count = (await db.execute(
        select(func.count()).where(Notebook.user_id == current_user.id)
    )).scalar_one()

    month_q = (await db.execute(
        select(func.count()).where(
            QueryEvent.user_id == current_user.id,
            QueryEvent.created_at >= month_start,
        )
    )).scalar_one()

    month_u = (await db.execute(
        select(func.count()).where(
            UploadEvent.user_id == current_user.id,
            UploadEvent.created_at >= month_start,
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

@router.post("/me/api-key/rotate", response_model=dict)
async def rotate_api_key(current_user: User = Depends(get_current_user)):
    current_user.api_key = str(uuid.uuid4())
    return {"api_key": current_user.api_key}
