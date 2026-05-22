"""JWT refresh-token blacklist backed by Redis.

Stores revoked JTIs as Redis keys with TTL = refresh token TTL.
Gracefully no-ops if Redis is unavailable (tokens expire naturally instead).
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# 30 days in seconds — must match REFRESH_TTL in jwt.py
_REFRESH_TTL_SEC = 60 * 60 * 24 * 30
_PREFIX = "jti_blacklist:"


class TokenBlacklist:
    def __init__(self, url: str | None = None) -> None:
        self._url = url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self._client = None
        self._connect()

    def _connect(self) -> None:
        try:
            import redis
            self._client = redis.from_url(self._url, decode_responses=True, socket_timeout=1)
            self._client.ping()
        except Exception as e:
            logger.warning(f"TokenBlacklist: Redis unavailable ({e}) — JTI revocation disabled")
            self._client = None

    def revoke(self, jti: str) -> None:
        """Mark a JTI as revoked. Silently skipped if Redis is down."""
        if self._client is None:
            return
        try:
            self._client.setex(f"{_PREFIX}{jti}", _REFRESH_TTL_SEC, "1")
        except Exception as e:
            logger.debug(f"TokenBlacklist.revoke error: {e}")

    def is_revoked(self, jti: str) -> bool:
        """Return True if this JTI has been revoked (or if Redis is down — fail-open)."""
        if self._client is None:
            return False
        try:
            return self._client.exists(f"{_PREFIX}{jti}") == 1
        except Exception as e:
            logger.debug(f"TokenBlacklist.is_revoked error: {e}")
            return False


token_blacklist = TokenBlacklist()
