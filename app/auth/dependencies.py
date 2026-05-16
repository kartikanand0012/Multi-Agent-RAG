"""FastAPI dependencies for authentication."""
from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import decode_token
from app.db.models import User
from app.db.session import get_db

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

_UNAUTH = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    creds:   HTTPAuthorizationCredentials | None = Security(_bearer),
    api_key: str | None                          = Security(_api_key_header),
    db:      AsyncSession                        = Depends(get_db),
) -> User:
    """
    Accepts either:
      - Authorization: Bearer <jwt>
      - X-API-Key: <uuid>
    """
    if creds:
        return await _user_from_jwt(creds.credentials, db)
    if api_key:
        return await _user_from_api_key(api_key, db)
    raise _UNAUTH


async def _user_from_jwt(token: str, db: AsyncSession) -> User:
    try:
        payload = decode_token(token)
    except JWTError:
        raise _UNAUTH

    if payload.get("type") != "access":
        raise _UNAUTH

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise _UNAUTH
    return user


async def _user_from_api_key(key: str, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.api_key == key))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise _UNAUTH
    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user
