"""Role-based access control FastAPI dependencies.

Roles live in the DB (roles / user_roles tables). The JWT access token carries
a 'roles' claim so hot-path checks don't hit the DB on every request.

Usage:
    @router.get("/admin/...")
    async def endpoint(user = Depends(require_role("admin"))):
        ...

    @router.get("/sensitive")
    async def endpoint(user = Depends(require_permission("admin.view_costs"))):
        ...
"""
from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.db.models import User

_FORBIDDEN = HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


def require_role(role_name: str):
    """Dependency factory: 403 unless current user has the given role."""
    async def _check(user: User = Depends(get_current_user)) -> User:
        if role_name not in user.roles:
            raise _FORBIDDEN
        return user
    _check.__name__ = f"require_role_{role_name}"
    return _check


def require_permission(permission_code: str):
    """Dependency factory: 403 unless the user's roles grant this permission."""
    async def _check(user: User = Depends(get_current_user)) -> User:
        from sqlalchemy import select
        # Import lazily to avoid circular imports; only runs on protected routes
        from app.db.models import Permission, RolePermission, Role, UserRole

        # Fast-path: admin always passes
        if "admin" in user.roles:
            return user

        # Fetch whether any of the user's roles have the required permission
        from app.db.session import get_db
        # We re-check from DB for permission-level decisions (security-critical)
        # roles claim in JWT is used for speed; permission check always hits DB
        # This is called infrequently (admin-only endpoints), so the query is fine
        raise _FORBIDDEN   # placeholder — full permission check wired after schema settles

    _check.__name__ = f"require_permission_{permission_code}"
    return _check


# Back-compat alias: existing code uses require_admin directly
async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise _FORBIDDEN
    return user
