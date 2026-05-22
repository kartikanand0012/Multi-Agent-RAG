"""Integration: register → login → me → refresh → logout."""
import pytest


@pytest.mark.asyncio
async def test_register_and_login(client, db):
    # Register
    r = await client.post("/api/v1/auth/register", json={
        "email": "alice@example.com", "username": "alice", "password": "Alice1234",
    })
    assert r.status_code == 201
    tokens = r.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens


@pytest.mark.asyncio
async def test_login_bad_password(client, user_factory):
    user = await user_factory()
    r = await client.post("/api/v1/auth/login", json={"email": user["email"], "password": "wrong"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_authenticated(client, user_factory):
    user = await user_factory()
    r = await client.post("/api/v1/auth/login", json={"email": user["email"], "password": "Password1"})
    token = r.json()["access_token"]

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["profile"]["email"] == user["email"]


@pytest.mark.asyncio
async def test_refresh_token(client, user_factory):
    user = await user_factory()
    r = await client.post("/api/v1/auth/login", json={"email": user["email"], "password": "Password1"})
    refresh = r.json()["refresh_token"]

    r2 = await client.post("/api/v1/auth/refresh", params={"refresh_token": refresh})
    assert r2.status_code == 200
    assert "access_token" in r2.json()


@pytest.mark.asyncio
async def test_logout_invalidates_token(client, user_factory):
    user = await user_factory()
    r = await client.post("/api/v1/auth/login", json={"email": user["email"], "password": "Password1"})
    refresh = r.json()["refresh_token"]

    logout = await client.post("/api/v1/auth/logout", params={"refresh_token": refresh})
    assert logout.status_code == 204

    # Revoked refresh should fail
    r2 = await client.post("/api/v1/auth/refresh", params={"refresh_token": refresh})
    assert r2.status_code == 401


@pytest.mark.asyncio
async def test_api_key_lifecycle(client, user_factory):
    user = await user_factory()
    r = await client.post("/api/v1/auth/login", json={"email": user["email"], "password": "Password1"})
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create
    create = await client.post("/api/v1/auth/me/api-keys", json={"label": "test-key"}, headers=headers)
    assert create.status_code == 201
    data = create.json()
    assert "key" in data  # plaintext shown once
    key_id = data["id"]
    raw_key = data["key"]

    # List
    lst = await client.get("/api/v1/auth/me/api-keys", headers=headers)
    assert any(k["id"] == key_id for k in lst.json())

    # Use key
    me = await client.get("/api/v1/auth/me", headers={"X-API-Key": raw_key})
    assert me.status_code == 200

    # Revoke
    rev = await client.delete(f"/api/v1/auth/me/api-keys/{key_id}", headers=headers)
    assert rev.status_code == 204

    # Key no longer works
    me2 = await client.get("/api/v1/auth/me", headers={"X-API-Key": raw_key})
    assert me2.status_code == 401
