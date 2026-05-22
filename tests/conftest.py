"""Shared pytest fixtures for unit and integration tests.

DB strategy:
  - Tables are created once per session with a sync wrapper around asyncio.run()
    so the session-scoped setup doesn't conflict with function-scoped event_loop.
  - Each test runs in a rolled-back transaction for full isolation.

LLM:
  - All LLM calls are monkeypatched to return stubs (no real Azure calls, no tokens).
"""
from __future__ import annotations

import asyncio
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── In-memory SQLite test engine ──────────────────────────────────────────────
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
_test_engine  = create_async_engine(TEST_DB_URL, echo=False, future=True)
_TestSession  = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)


# ── One-time table setup/teardown — SYNC fixture using asyncio.run() ──────────
# Using a sync fixture avoids the ScopeMismatch that arises when a session-scoped
# async fixture tries to borrow the function-scoped event_loop.
@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    from app.db.base import Base
    from app.db import models  # noqa — registers all ORM classes

    async def _setup():
        async with _test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def _teardown():
        async with _test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    asyncio.run(_setup())
    yield
    asyncio.run(_teardown())


# ── Per-test DB session (rolled back after each test) ─────────────────────────
@pytest_asyncio.fixture()
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with _TestSession() as session:
        await session.begin()
        try:
            yield session
        finally:
            await session.rollback()


# ── App + HTTPX client ────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def _app():
    from app.api.main import create_app
    return create_app()


@pytest_asyncio.fixture()
async def client(_app, db) -> AsyncGenerator[AsyncClient, None]:
    from app.db.session import get_db

    async def _override_db():
        yield db

    _app.dependency_overrides[get_db] = _override_db
    async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://test") as c:
        yield c
    _app.dependency_overrides.clear()


# ── User factories ────────────────────────────────────────────────────────────
@pytest_asyncio.fixture()
async def user_factory(db: AsyncSession):
    from app.auth.password import hash_password
    from app.db.models import Quota, QuotaPeriod, User

    async def _make(email: str | None = None, is_admin: bool = False) -> dict:
        email    = email or f"test-{uuid.uuid4().hex[:8]}@example.com"
        username = f"user_{uuid.uuid4().hex[:6]}"
        user = User(
            id=str(uuid.uuid4()),   # explicit id so Quota FK is set before flush
            email=email, username=username,
            hashed_password=hash_password("Password1"),
            is_admin=is_admin,
        )
        db.add(user)
        await db.flush()  # user PK must exist before Quota inserts it as FK

        db.add(Quota(
            user_id=user.id, period=QuotaPeriod.daily,
            max_queries=200, max_uploads=20, max_tokens=500_000,
        ))
        await db.flush()
        return {"id": user.id, "email": email, "username": username}

    return _make


@pytest_asyncio.fixture()
async def admin_factory(db: AsyncSession, user_factory):
    async def _make():
        return await user_factory(email="kartikanand0012@gmail.com", is_admin=True)
    return _make


# ── Auth helpers ──────────────────────────────────────────────────────────────
@pytest.fixture()
def auth_headers(client):
    async def _login(email: str, password: str = "Password1") -> dict:
        r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}
    return _login


# ── LLM stub — prevents any real Azure/OpenAI calls ──────────────────────────
@pytest.fixture(autouse=True)
def stub_llm(monkeypatch):
    import app.llm.client as llm_module

    class _FakeLLM:
        strong_model = "stub-gpt4o"
        fast_model   = "stub-gpt4o-mini"

        async def complete(self, messages, **_):
            return '{"passed": true, "unsupported_claims": [], "feedback": "All claims verified."}'

        async def stream(self, messages, **_):
            for token in ["Hello ", "from ", "stub."]:
                yield token

        async def embed(self, texts):
            return [[0.1] * 1536 for _ in texts]

    monkeypatch.setattr(llm_module, "llm_client", _FakeLLM())
