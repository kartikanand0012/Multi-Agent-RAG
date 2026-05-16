"""JWT creation and verification."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.core.config import settings

ALGORITHM = "HS256"
ACCESS_TTL  = timedelta(minutes=15)
REFRESH_TTL = timedelta(days=30)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub":   user_id,
        "email": email,
        "type":  "access",
        "jti":   str(uuid.uuid4()),
        "iat":   _now(),
        "exp":   _now() + ACCESS_TTL,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_refresh_token(user_id: str) -> tuple[str, str]:
    """Returns (token, jti) — store jti in Redis for invalidation."""
    jti = str(uuid.uuid4())
    payload = {
        "sub":  user_id,
        "type": "refresh",
        "jti":  jti,
        "iat":  _now(),
        "exp":  _now() + REFRESH_TTL,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM), jti


def decode_token(token: str) -> dict:
    """Raises JWTError on invalid/expired token."""
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
