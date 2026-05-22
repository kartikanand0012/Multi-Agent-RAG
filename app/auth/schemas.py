"""Auth request/response schemas."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email:     EmailStr
    username:  str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_\-]+$")
    password:  str = Field(..., min_length=8, max_length=128)
    full_name: str = Field("", max_length=120)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    email:    EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"


class UserProfile(BaseModel):
    id:            str
    email:         str
    username:      str
    full_name:     str
    is_admin:      bool
    roles:         List[str] = []
    created_at:    datetime
    last_login_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UserStats(BaseModel):
    total_queries:      int
    total_uploads:      int
    notebooks_count:    int
    queries_this_month: int
    uploads_this_month: int


class UserMeResponse(BaseModel):
    profile: UserProfile
    stats:   UserStats


class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = Field(None, max_length=120)
    username:  Optional[str] = Field(None, min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_\-]+$")


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


# ── API key schemas ────────────────────────────────────────────────────────────

class ApiKeyCreate(BaseModel):
    label: str = Field("", max_length=80)


class ApiKeyOut(BaseModel):
    id:           str
    label:        str
    last_used_at: Optional[datetime] = None
    expires_at:   Optional[datetime] = None
    created_at:   datetime

    model_config = {"from_attributes": True}


class ApiKeyCreated(ApiKeyOut):
    """Includes the plaintext key — shown once only at creation."""
    key: str
