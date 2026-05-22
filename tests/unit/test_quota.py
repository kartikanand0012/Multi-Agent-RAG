"""Unit: quota math — reset window detection."""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from app.db.models import Quota, QuotaPeriod, User


def _make_quota(used_queries=0, max_queries=200, resets_at=None) -> Quota:
    now = datetime.now(timezone.utc)
    q = Quota(
        id="q1", user_id="u1",
        period=QuotaPeriod.daily,
        max_queries=max_queries,
        max_uploads=20,
        max_tokens=500_000,
        used_queries=used_queries,
        used_uploads=0,
        used_tokens=0,
        resets_at=resets_at or (now + timedelta(hours=12)),
    )
    return q


@pytest.mark.asyncio
async def test_quota_ok(monkeypatch):
    """Under-limit user passes check."""
    from app.middleware.quota import check_query_quota
    quota = _make_quota(used_queries=50)

    user = MagicMock(spec=User)
    user.is_admin = False
    user.id = "u1"

    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: quota))

    # Should not raise
    await check_query_quota(user, db)


@pytest.mark.asyncio
async def test_quota_exceeded(monkeypatch):
    """At-limit user gets 429."""
    from fastapi import HTTPException
    from app.middleware.quota import check_query_quota

    quota = _make_quota(used_queries=200, max_queries=200)

    user = MagicMock(spec=User)
    user.is_admin = False
    user.id = "u1"

    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: quota))

    with pytest.raises(HTTPException) as exc:
        await check_query_quota(user, db)
    assert exc.value.status_code == 429


def test_admin_bypasses_quota(monkeypatch):
    """Admins skip quota checks."""
    import asyncio
    from app.middleware.quota import check_query_quota

    user = MagicMock(spec=User)
    user.is_admin = True
    db = MagicMock()

    # Should complete without touching DB
    asyncio.run(check_query_quota(user, db))
    db.execute.assert_not_called()
