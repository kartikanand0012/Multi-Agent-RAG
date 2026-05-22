"""Integration: admin endpoints require is_admin; non-admin gets 403."""
import pytest


@pytest.mark.asyncio
async def test_overview_admin_only(client, user_factory):
    user = await user_factory()
    r = await client.post("/api/v1/auth/login", json={"email": user["email"], "password": "Password1"})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    resp = await client.get("/api/v1/admin/overview", headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_overview_as_admin(client, user_factory):
    admin = await user_factory(is_admin=True)
    r = await client.post("/api/v1/auth/login", json={"email": admin["email"], "password": "Password1"})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    resp = await client.get("/api/v1/admin/overview", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "users" in body
    assert "queries" in body


@pytest.mark.asyncio
async def test_list_users_as_admin(client, user_factory):
    admin = await user_factory(is_admin=True)
    # Create a regular user too
    await user_factory()

    r = await client.post("/api/v1/auth/login", json={"email": admin["email"], "password": "Password1"})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    resp = await client.get("/api/v1/admin/users", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 2


@pytest.mark.asyncio
async def test_quota_update(client, user_factory):
    admin  = await user_factory(is_admin=True)
    target = await user_factory()

    r = await client.post("/api/v1/auth/login", json={"email": admin["email"], "password": "Password1"})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    resp = await client.patch(
        f"/api/v1/admin/users/{target['id']}/quota",
        params={"max_queries": 5},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["max_queries"] == 5
