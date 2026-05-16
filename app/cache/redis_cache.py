"""Redis query result cache with graceful degradation.

If Redis is unavailable, all cache operations are silent no-ops —
the system continues working without caching.

Cache keys:
  query_result:<sha256(query+notebook_id)> → JSON response (TTL 1h)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

QUERY_TTL = 3600        # 1 hour


def _make_key(query: str, notebook_id: str) -> str:
    raw = f"{query.strip().lower()}::{notebook_id}"
    return "query_result:" + hashlib.sha256(raw.encode()).hexdigest()


class QueryCache:
    """Thread-safe Redis cache for full query responses."""

    def __init__(self, url: str | None = None) -> None:
        self._url = url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self._client = None
        self._connect()

    def _connect(self) -> None:
        try:
            import redis
            self._client = redis.from_url(self._url, decode_responses=True, socket_timeout=1)
            self._client.ping()
            logger.info(f"Redis connected: {self._url}")
        except Exception as e:
            logger.warning(f"Redis unavailable ({e}) — caching disabled, system still works")
            self._client = None

    def get(self, query: str, notebook_id: str) -> Optional[dict]:
        if self._client is None:
            return None
        try:
            key = _make_key(query, notebook_id)
            raw = self._client.get(key)
            if raw:
                logger.info(f"Cache HIT: {key[:20]}...")
                return json.loads(raw)
        except Exception as e:
            logger.debug(f"Cache get error: {e}")
        return None

    def set(self, query: str, notebook_id: str, value: dict) -> None:
        if self._client is None:
            return
        try:
            key = _make_key(query, notebook_id)
            self._client.setex(key, QUERY_TTL, json.dumps(value))
            logger.info(f"Cache SET: {key[:20]}... (TTL {QUERY_TTL}s)")
        except Exception as e:
            logger.debug(f"Cache set error: {e}")

    def invalidate(self, notebook_id: str) -> int:
        """Delete all cached queries for a notebook (called on re-ingest)."""
        if self._client is None:
            return 0
        try:
            keys = self._client.keys("query_result:*")
            deleted = 0
            for key in keys:
                self._client.delete(key)
                deleted += 1
            return deleted
        except Exception as e:
            logger.debug(f"Cache invalidate error: {e}")
            return 0

    @property
    def is_available(self) -> bool:
        return self._client is not None


# Module-level singleton
query_cache = QueryCache()
