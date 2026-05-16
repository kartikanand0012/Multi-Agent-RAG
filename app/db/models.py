"""ORM models for users, notebooks, and analytics events."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


# ── Users ──────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id:               Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email:            Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username:         Mapped[str] = mapped_column(String(50),  unique=True, nullable=False, index=True)
    hashed_password:  Mapped[str] = mapped_column(Text, nullable=False)
    full_name:        Mapped[str] = mapped_column(String(120), nullable=False, default="")
    is_active:        Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin:         Mapped[bool] = mapped_column(Boolean, default=False)
    api_key:          Mapped[str] = mapped_column(String(36), unique=True, default=_uuid, index=True)
    created_at:       Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_login_at:    Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # relationships
    notebooks:     Mapped[list[Notebook]]    = relationship("Notebook",    back_populates="user", cascade="all, delete-orphan")
    query_events:  Mapped[list[QueryEvent]]  = relationship("QueryEvent",  back_populates="user", cascade="all, delete-orphan")
    upload_events: Mapped[list[UploadEvent]] = relationship("UploadEvent", back_populates="user", cascade="all, delete-orphan")


# ── Notebooks ──────────────────────────────────────────────────────────────────

class Notebook(Base):
    __tablename__ = "notebooks"

    id:         Mapped[str]      = mapped_column(String(64),  primary_key=True)
    name:       Mapped[str]      = mapped_column(String(200), nullable=False)
    user_id:    Mapped[str]      = mapped_column(String(36),  ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    doc_count:  Mapped[int]      = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    user: Mapped[User] = relationship("User", back_populates="notebooks")


# ── Analytics ──────────────────────────────────────────────────────────────────

class QueryEvent(Base):
    __tablename__ = "query_events"

    id:                Mapped[str]      = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id:           Mapped[str]      = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    notebook_id:       Mapped[str]      = mapped_column(String(64), nullable=False, index=True)
    query_text:        Mapped[str]      = mapped_column(Text, nullable=False)
    intent_type:       Mapped[str]      = mapped_column(String(50), nullable=False, default="unknown")
    sub_queries_count: Mapped[int]      = mapped_column(Integer, default=1)
    sources_found:     Mapped[int]      = mapped_column(Integer, default=0)
    tokens_estimated:  Mapped[int]      = mapped_column(Integer, default=0)
    validation_passed: Mapped[bool]     = mapped_column(Boolean, default=True)
    retry_count:       Mapped[int]      = mapped_column(Integer, default=0)
    cached:            Mapped[bool]     = mapped_column(Boolean, default=False)
    latency_ms:        Mapped[int]      = mapped_column(Integer, default=0)
    created_at:        Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    user: Mapped[User] = relationship("User", back_populates="query_events")


class UploadEvent(Base):
    __tablename__ = "upload_events"

    id:                Mapped[str]      = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id:           Mapped[str]      = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    notebook_id:       Mapped[str]      = mapped_column(String(64), nullable=False, index=True)
    original_filename: Mapped[str]      = mapped_column(String(500), nullable=False)
    file_size_bytes:   Mapped[int]      = mapped_column(Integer, default=0)
    total_nodes:       Mapped[int]      = mapped_column(Integer, default=0)
    leaf_chunks:       Mapped[int]      = mapped_column(Integer, default=0)
    use_raptor:        Mapped[bool]     = mapped_column(Boolean, default=True)
    processing_ms:     Mapped[int]      = mapped_column(Integer, default=0)
    created_at:        Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    user: Mapped[User] = relationship("User", back_populates="upload_events")
