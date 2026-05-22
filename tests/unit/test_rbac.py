"""Unit: RBAC roles list derivation from user_roles relationship."""
import pytest


def test_user_roles_property():
    """User.roles returns a list of role names from role_assignments."""
    from app.db.models import Role, User, UserRole

    user = User(id="u1", email="a@b.com", username="a", hashed_password="x")
    role = Role(id=1, name="admin", description="")

    ur = UserRole(user_id="u1", role_id=1)
    ur.role = role  # simulate the joined relationship

    user.role_assignments = [ur]
    assert user.roles == ["admin"]


def test_user_without_roles():
    from app.db.models import User
    user = User(id="u2", email="b@c.com", username="b", hashed_password="x")
    user.role_assignments = []
    assert user.roles == []
