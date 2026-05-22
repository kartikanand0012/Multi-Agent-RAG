"""Shared pytest fixtures for unit and integration tests.

DB: each test runs in a transaction that is rolled back on teardown —
no need to create/drop tables between tests.

LLM: Azure calls are monkeypatched to return deterministic stubs so tests
run without real credentials and don't consume tokens.
"""
from __future__ import annotations

import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── Async mode ────────────────────────────────────────────────────────────────
# pyproject.toml already sets asyncio_mode = "auto"


# ── In-memory SQLite for tests ────────────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

_test_engine = create_async_engine(TEST_DB_URL, echo=False, future=True)
_TestSession  = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_tables():
    """Create all tables once for the test session."""
    from app.db.base import Base
    from app.db import models  # noqa — register all models
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture()
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Yields a rolled-back session per test."""
    async with _TestSession() as session:
        await session.begin()
        try:
            yield session
        finally:
            await session.rollback()


# ── App + HTTP client ─────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def _app():
    """Create the FastAPI app once; override DB session dependency."""
    from app.api.main import create_app
    return create_app()


@pytest_asyncio.fixture()
async def client(_app, db) -> AsyncGenerator[AsyncClient, None]:
    """HTTPX async client wired to the test app + test DB session."""
    from app.db.session import get_db

    # get_db is an async generator — the override must also be one
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
        # Give the user an explicit id so it's available before the flush
        user_id = str(uuid.uuid4())
        user = User(
            id=user_id, email=email, username=username,
            hashed_password=hash_password("Password1"),
            is_admin=is_admin,
        )
        db.add(user)
        await db.flush()  # flush user first so its PK exists before Quota FK

        db.add(Quota(user_id=user.id, period=QuotaPeriod.daily))
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


# ── LLM stub (prevents real Azure calls) ─────────────────────────────────────

@pytest.fixture(autouse=True)
def stub_llm(monkeypatch):
    """Replace LLM calls with deterministic stubs for all tests."""
    import app.llm.client as llm_module

    class _FakeClient:
        strong_model = "stub-gpt4o"
        fast_model   = "stub-gpt4o-mini"

        async def complete(self, messages, **_):
            return '{"passed": true, "unsupported_claims": [], "feedback": "All claims verified."}'

        async def stream(self, messages, **_):
            for token in ["Hello ", "from ", "stub."]:
                yield token

        async def embed(self, texts):
            return [[0.1] * 1536 for _ in texts]

        def count_tokens(self, text):
            return len(text.split())

    monkeypatch.setattr(llm_module, "llm_client", _FakeClient())
