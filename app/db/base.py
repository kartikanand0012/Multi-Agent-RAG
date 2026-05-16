"""SQLAlchemy async engine — SQLite for dev/test, PostgreSQL for production."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


def _make_engine():
    url = settings.database_url
    kwargs: dict = {"echo": settings.environment == "development"}

    if url.startswith("sqlite"):
        # SQLite needs check_same_thread=False in connect args
        kwargs["connect_args"] = {"check_same_thread": False}

    return create_async_engine(url, **kwargs)


engine = _make_engine()

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass
