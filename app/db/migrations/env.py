"""Alembic env — async engine (asyncpg) for migrations.

Uses SQLAlchemy's async_engine_from_config so the same asyncpg driver
the app uses is also used here — no psycopg2 needed.
"""
from __future__ import annotations

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# Make `app` importable when running `alembic` from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db import models  # noqa: F401,E402  — register all models

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Ensure the URL uses the asyncpg driver.
# Railway provides postgresql:// or postgres:// — rewrite both.
url = settings.database_url
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql+asyncpg://", 1)
elif url.startswith("postgresql://") and "+asyncpg" not in url:
    url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
# SQLite (dev/test) stays as-is for offline mode
config.set_main_option("sqlalchemy.url", url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL without a live DB connection (used for SQL script output)."""
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
