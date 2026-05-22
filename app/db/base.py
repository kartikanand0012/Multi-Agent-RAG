"""SQLAlchemy 2.0 async engine — sized for ~10 concurrent users.

Postgres in production (asyncpg driver), SQLite for dev/test.
Pool is generous enough that streaming requests + Celery worker won't starve
each other, but conservative enough to stay under Postgres's default 100 max.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import settings


def _make_engine():
    url = settings.database_url
    kwargs: dict = {"echo": False, "future": True}

    if url.startswith("sqlite"):
        # SQLite: in-process, single-connection; aiosqlite handles the threading
        kwargs["connect_args"] = {"check_same_thread": False}
        kwargs["poolclass"] = NullPool
    else:
        # Postgres / asyncpg: sized for 10 web workers + headroom for Celery
        kwargs.update(
            pool_size=10,
            max_overflow=10,
            pool_pre_ping=True,        # detect dropped connections before use
            pool_recycle=1800,         # recycle every 30 min (Railway terminates idle conns)
        )

    return create_async_engine(url, **kwargs)


engine = _make_engine()

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Declarative base for all ORM models. See app.db.models."""
    pass
