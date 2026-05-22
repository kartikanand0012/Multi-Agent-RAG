"""Seed roles, permissions, and promote the admin user.

Run once on a fresh DB:
    python scripts/seed_roles.py

Safe to re-run — uses INSERT OR IGNORE (SQLite) / ON CONFLICT DO NOTHING (Postgres).
"""
import asyncio
import sys
from pathlib import Path

# Allow importing the app from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.models import Permission, Role, RolePermission, User, UserRole

ROLES = [
    {"name": "admin",   "description": "Full access to all resources and admin dashboard"},
    {"name": "user",    "description": "Standard user — query and upload within quota"},
    {"name": "analyst", "description": "Read-only access to analytics and query history"},
]

PERMISSIONS = [
    ("admin.view_all_users",   "View any user's profile and history"),
    ("admin.view_costs",       "View per-user cost and token usage"),
    ("admin.manage_quotas",    "Adjust per-user quotas"),
    ("admin.manage_roles",     "Grant or revoke user roles"),
    ("admin.view_alerts",      "View system alerts inbox"),
    ("admin.resolve_alerts",   "Mark alerts as resolved"),
    ("admin.view_audit_log",   "Read the audit log"),
    ("notebook.create",        "Create notebooks"),
    ("notebook.delete_own",    "Delete own notebooks"),
    ("notebook.delete_any",    "Delete any user's notebook"),
    ("query.stream",           "Submit streaming queries"),
    ("upload.document",        "Upload documents"),
]

# Which permissions each role gets
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "admin":   [p[0] for p in PERMISSIONS],   # admin gets everything
    "analyst": ["admin.view_all_users", "admin.view_costs", "admin.view_audit_log",
                "admin.view_alerts"],
    "user":    ["notebook.create", "notebook.delete_own", "query.stream", "upload.document"],
}


async def _upsert_role(db: AsyncSession, name: str, description: str) -> Role:
    result = await db.execute(select(Role).where(Role.name == name))
    role = result.scalar_one_or_none()
    if not role:
        role = Role(name=name, description=description)
        db.add(role)
        await db.flush()
        print(f"  Created role: {name}")
    return role


async def _upsert_permission(db: AsyncSession, code: str, description: str) -> Permission:
    result = await db.execute(select(Permission).where(Permission.code == code))
    perm = result.scalar_one_or_none()
    if not perm:
        perm = Permission(code=code, description=description)
        db.add(perm)
        await db.flush()
        print(f"  Created permission: {code}")
    return perm


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        print("Seeding roles...")
        role_map: dict[str, Role] = {}
        for r in ROLES:
            role_map[r["name"]] = await _upsert_role(db, r["name"], r["description"])

        print("Seeding permissions...")
        perm_map: dict[str, Permission] = {}
        for code, description in PERMISSIONS:
            perm_map[code] = await _upsert_permission(db, code, description)

        print("Wiring role→permission grants...")
        for role_name, perm_codes in ROLE_PERMISSIONS.items():
            role = role_map[role_name]
            for code in perm_codes:
                perm = perm_map[code]
                existing = await db.execute(
                    select(RolePermission).where(
                        RolePermission.role_id == role.id,
                        RolePermission.permission_id == perm.id,
                    )
                )
                if not existing.scalar_one_or_none():
                    db.add(RolePermission(role_id=role.id, permission_id=perm.id))
            print(f"  {role_name}: {len(perm_codes)} permissions")

        print(f"\nPromoting admin user: {settings.admin_email}")
        user_result = await db.execute(select(User).where(User.email == settings.admin_email))
        admin_user = user_result.scalar_one_or_none()
        if admin_user:
            admin_user.is_admin = True
            admin_role = role_map["admin"]
            existing_role = await db.execute(
                select(UserRole).where(
                    UserRole.user_id == admin_user.id,
                    UserRole.role_id == admin_role.id,
                )
            )
            if not existing_role.scalar_one_or_none():
                db.add(UserRole(user_id=admin_user.id, role_id=admin_role.id))
                print(f"  Admin role granted to {settings.admin_email}")
            else:
                print(f"  {settings.admin_email} already has admin role")
        else:
            print(f"  User {settings.admin_email} not found — register first, then re-run this script.")

        await db.commit()
        print("\nDone.")


if __name__ == "__main__":
    asyncio.run(seed())
