"""SQLAlchemy 2.0 ORM models — Phase 2 schema.

Naming: snake_case tables, FKs cascade where the parent owns the child,
JSON for flexible blobs (becomes JSONB on Postgres), Numeric for money.

Relationship overview:
    User ─┬─ Notebook ─┬─ Conversation ─ Message ─ AgentRun ─┬─ AgentStep
          │            │                                      ├─ RetrievedChunk
          │            └─ IngestionJob                        └─ UsageEvent
          ├─ ApiKey
          ├─ UserRole ── Role ── RolePermission ── Permission
          ├─ Quota
          ├─ UsageEvent
          └─ AuditLog
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON, Boolean, DateTime, Enum, ForeignKey, Index, Integer, Numeric,
    String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


# ── Enums ─────────────────────────────────────────────────────────────────────

class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class AgentName(str, enum.Enum):
    intent = "intent"
    retrieval = "retrieval"
    reasoning = "reasoning"
    validation = "validation"


class RunStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class JobStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    done = "done"
    failed = "failed"


class NotebookStatus(str, enum.Enum):
    active = "active"
    archived = "archived"
    deleting = "deleting"


class UsageEventType(str, enum.Enum):
    query = "query"
    upload = "upload"
    embedding = "embedding"


class QuotaPeriod(str, enum.Enum):
    daily = "daily"
    monthly = "monthly"


class AlertSeverity(str, enum.Enum):
    info = "info"
    warn = "warn"
    error = "error"
    critical = "critical"


# ── RBAC ──────────────────────────────────────────────────────────────────────

class Role(Base):
    __tablename__ = "roles"

    id:          Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    name:        Mapped[str]      = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str]      = mapped_column(String(255), default="")
    created_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    permissions: Mapped[list[Permission]] = relationship(
        "Permission", secondary="role_permissions", back_populates="roles", lazy="selectin",
    )


class Permission(Base):
    __tablename__ = "permissions"

    id:          Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    code:        Mapped[str]      = mapped_column(String(80), unique=True, nullable=False, index=True)
    description: Mapped[str]      = mapped_column(String(255), default="")
    created_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    roles: Mapped[list[Role]] = relationship(
        "Role", secondary="role_permissions", back_populates="permissions",
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id:       Mapped[int] = mapped_column(ForeignKey("roles.id",       ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id:    Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id:    Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    granted_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    role: Mapped[Role] = relationship("Role", lazy="joined")
    user: Mapped[User] = relationship("User", foreign_keys=[user_id], back_populates="role_assignments")


# ── User & friends ────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id:              Mapped[str]      = mapped_column(String(36), primary_key=True, default=_uuid)
    email:           Mapped[str]      = mapped_column(String(255), unique=True, nullable=False, index=True)
    username:        Mapped[str]      = mapped_column(String(50),  unique=True, nullable=False, index=True)
    hashed_password: Mapped[str]      = mapped_column(Text, nullable=False)
    full_name:       Mapped[str]      = mapped_column(String(120), nullable=False, default="")
    is_active:       Mapped[bool]     = mapped_column(Boolean, default=True)
    # Kept as a denormalised flag for hot-path checks; mirrors user_roles ↔ 'admin'
    is_admin:        Mapped[bool]     = mapped_column(Boolean, default=False, index=True)
    created_at:      Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_login_at:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    role_assignments: Mapped[list[UserRole]]      = relationship("UserRole", foreign_keys=[UserRole.user_id], back_populates="user", cascade="all, delete-orphan", lazy="selectin")
    api_keys:         Mapped[list[ApiKey]]        = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")
    notebooks:        Mapped[list[Notebook]]      = relationship("Notebook", back_populates="user", cascade="all, delete-orphan")
    conversations:    Mapped[list[Conversation]]  = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    quotas:           Mapped[list[Quota]]         = relationship("Quota", back_populates="user", cascade="all, delete-orphan")
    audit_logs:       Mapped[list[AuditLog]]      = relationship("AuditLog", foreign_keys="AuditLog.user_id", back_populates="user", cascade="all, delete-orphan")

    @property
    def roles(self) -> list[str]:
        return [ra.role.name for ra in self.role_assignments]


class ApiKey(Base):
    __tablename__ = "api_keys"

    id:            Mapped[str]      = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id:       Mapped[str]      = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    key_hash:      Mapped[str]      = mapped_column(String(64), unique=True, nullable=False, index=True)  # sha256 hex
    label:         Mapped[str]      = mapped_column(String(80), default="")
    last_used_at:  Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at:    Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at:    Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped[User] = relationship("User", back_populates="api_keys")


# ── Notebooks ─────────────────────────────────────────────────────────────────

class Notebook(Base):
    __tablename__ = "notebooks"

    id:                 Mapped[str]      = mapped_column(String(64), primary_key=True)
    name:               Mapped[str]      = mapped_column(String(200), nullable=False)
    user_id:            Mapped[str]      = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    doc_count:          Mapped[int]      = mapped_column(Integer, default=0)
    total_chunks:       Mapped[int]      = mapped_column(Integer, default=0)
    total_tokens_used:  Mapped[int]      = mapped_column(Integer, default=0)
    status:             Mapped[NotebookStatus] = mapped_column(Enum(NotebookStatus, name="notebook_status"), default=NotebookStatus.active)
    last_queried_at:    Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:         Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at:         Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    user:           Mapped[User]                = relationship("User", back_populates="notebooks")
    conversations:  Mapped[list[Conversation]]  = relationship("Conversation", back_populates="notebook", cascade="all, delete-orphan")
    ingestion_jobs: Mapped[list[IngestionJob]]  = relationship("IngestionJob", back_populates="notebook", cascade="all, delete-orphan")


# ── Conversation thread ───────────────────────────────────────────────────────

class Conversation(Base):
    __tablename__ = "conversations"

    id:              Mapped[str]      = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id:         Mapped[str]      = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    notebook_id:     Mapped[str]      = mapped_column(String(64), ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False, index=True)
    title:           Mapped[str]      = mapped_column(String(200), default="New conversation")
    message_count:   Mapped[int]      = mapped_column(Integer, default=0)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:      Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at:      Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    user:     Mapped[User]          = relationship("User", back_populates="conversations")
    notebook: Mapped[Notebook]      = relationship("Notebook", back_populates="conversations")
    messages: Mapped[list[Message]] = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at")

    __table_args__ = (
        Index("ix_conversations_user_created", "user_id", "created_at"),
    )


class Message(Base):
    __tablename__ = "messages"

    id:              Mapped[str]      = mapped_column(String(36), primary_key=True, default=_uuid)
    conversation_id: Mapped[str]      = mapped_column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role:            Mapped[MessageRole] = mapped_column(Enum(MessageRole, name="message_role"), nullable=False)
    content:         Mapped[str]      = mapped_column(Text, nullable=False)
    agent_run_id:    Mapped[str | None] = mapped_column(String(36), ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True)
    created_at:      Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    conversation: Mapped[Conversation] = relationship("Conversation", back_populates="messages")
    # Assistant messages link to the run that produced them
    agent_run:    Mapped[AgentRun | None] = relationship("AgentRun", back_populates="message", foreign_keys=[agent_run_id])

    __table_args__ = (
        Index("ix_messages_conv_created", "conversation_id", "created_at"),
    )


# ── Agent runs + per-agent steps ──────────────────────────────────────────────

class AgentRun(Base):
    __tablename__ = "agent_runs"

    id:                  Mapped[str]      = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id:             Mapped[str]      = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    notebook_id:         Mapped[str]      = mapped_column(String(64), ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False, index=True)

    query_text:          Mapped[str]      = mapped_column(Text, nullable=False)
    intent_type:         Mapped[str]      = mapped_column(String(50), default="unknown")
    sub_queries:         Mapped[dict | None] = mapped_column(JSON, nullable=True)   # list under JSON
    retry_count:         Mapped[int]      = mapped_column(Integer, default=0)
    sources_found:       Mapped[int]      = mapped_column(Integer, default=0)
    validation_passed:   Mapped[bool]     = mapped_column(Boolean, default=True)
    unsupported_claims:  Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation_feedback: Mapped[str]      = mapped_column(Text, default="")
    total_tokens_in:     Mapped[int]      = mapped_column(Integer, default=0)
    total_tokens_out:    Mapped[int]      = mapped_column(Integer, default=0)
    total_cost_usd:      Mapped[Decimal]  = mapped_column(Numeric(10, 6), default=Decimal("0"))
    latency_ms:          Mapped[int]      = mapped_column(Integer, default=0)
    langfuse_trace_id:   Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status:              Mapped[RunStatus] = mapped_column(Enum(RunStatus, name="run_status"), default=RunStatus.pending, index=True)
    error:               Mapped[str]      = mapped_column(Text, default="")
    cached:              Mapped[bool]     = mapped_column(Boolean, default=False)
    model_strong:        Mapped[str]      = mapped_column(String(50), default="")
    model_fast:          Mapped[str]      = mapped_column(String(50), default="")
    created_at:          Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at:         Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    message:           Mapped[Message | None]      = relationship("Message", back_populates="agent_run", uselist=False, foreign_keys=[Message.agent_run_id])
    steps:             Mapped[list[AgentStep]]     = relationship("AgentStep", back_populates="run", cascade="all, delete-orphan", order_by="AgentStep.step_order")
    retrieved_chunks:  Mapped[list[RetrievedChunk]] = relationship("RetrievedChunk", back_populates="run", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_agent_runs_user_created", "user_id", "created_at"),
        Index("ix_agent_runs_status_created", "status", "created_at"),
    )


class AgentStep(Base):
    __tablename__ = "agent_steps"

    id:              Mapped[str]      = mapped_column(String(36), primary_key=True, default=_uuid)
    agent_run_id:    Mapped[str]      = mapped_column(String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_name:      Mapped[AgentName] = mapped_column(Enum(AgentName, name="agent_name"), nullable=False)
    step_order:      Mapped[int]      = mapped_column(Integer, default=0)
    input_summary:   Mapped[str]      = mapped_column(Text, default="")
    output_summary:  Mapped[str]      = mapped_column(Text, default="")
    tokens_in:       Mapped[int]      = mapped_column(Integer, default=0)
    tokens_out:      Mapped[int]      = mapped_column(Integer, default=0)
    latency_ms:      Mapped[int]      = mapped_column(Integer, default=0)
    error:           Mapped[str]      = mapped_column(Text, default="")
    extra_metadata:  Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at:      Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    run: Mapped[AgentRun] = relationship("AgentRun", back_populates="steps")


class RetrievedChunk(Base):
    __tablename__ = "retrieved_chunks"

    id:                  Mapped[str]      = mapped_column(String(36), primary_key=True, default=_uuid)
    agent_run_id:        Mapped[str]      = mapped_column(String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id:            Mapped[str]      = mapped_column(String(80), nullable=False)
    chunk_text_preview:  Mapped[str]      = mapped_column(Text, default="")
    score:               Mapped[float]    = mapped_column(Numeric(8, 6), default=0)
    layer:               Mapped[int]      = mapped_column(Integer, default=0)
    source:              Mapped[str]      = mapped_column(String(500), default="")
    rank_position:       Mapped[int]      = mapped_column(Integer, default=0)

    run: Mapped[AgentRun] = relationship("AgentRun", back_populates="retrieved_chunks")


# ── Ingestion jobs (Celery-backed) ────────────────────────────────────────────

class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id:                Mapped[str]      = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id:           Mapped[str]      = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    notebook_id:       Mapped[str]      = mapped_column(String(64), ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False, index=True)
    original_filename: Mapped[str]      = mapped_column(String(500), nullable=False)
    file_size_bytes:   Mapped[int]      = mapped_column(Integer, default=0)
    status:            Mapped[JobStatus] = mapped_column(Enum(JobStatus, name="job_status"), default=JobStatus.queued, index=True)
    use_raptor:        Mapped[bool]     = mapped_column(Boolean, default=True)
    total_nodes:       Mapped[int]      = mapped_column(Integer, default=0)
    leaf_chunks:       Mapped[int]      = mapped_column(Integer, default=0)
    processing_ms:     Mapped[int]      = mapped_column(Integer, default=0)
    celery_task_id:    Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    error:             Mapped[str]      = mapped_column(Text, default="")
    queued_at:         Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at:        Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at:       Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    notebook: Mapped[Notebook] = relationship("Notebook", back_populates="ingestion_jobs")


# ── Usage / billing telemetry ─────────────────────────────────────────────────

class UsageEvent(Base):
    __tablename__ = "usage_events"

    id:                 Mapped[str]      = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id:            Mapped[str]      = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type:         Mapped[UsageEventType] = mapped_column(Enum(UsageEventType, name="usage_event_type"), nullable=False)
    agent_run_id:       Mapped[str | None] = mapped_column(String(36), ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True)
    ingestion_job_id:   Mapped[str | None] = mapped_column(String(36), ForeignKey("ingestion_jobs.id", ondelete="SET NULL"), nullable=True)
    tokens_in:          Mapped[int]      = mapped_column(Integer, default=0)
    tokens_out:         Mapped[int]      = mapped_column(Integer, default=0)
    cost_usd:           Mapped[Decimal]  = mapped_column(Numeric(10, 6), default=Decimal("0"))
    created_at:         Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    __table_args__ = (
        Index("ix_usage_user_created", "user_id", "created_at"),
        Index("ix_usage_type_created", "event_type", "created_at"),
    )


class Quota(Base):
    __tablename__ = "quotas"

    id:           Mapped[str]      = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id:      Mapped[str]      = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    period:       Mapped[QuotaPeriod] = mapped_column(Enum(QuotaPeriod, name="quota_period"), nullable=False, default=QuotaPeriod.daily)
    max_queries:  Mapped[int]      = mapped_column(Integer, default=200)
    max_uploads:  Mapped[int]      = mapped_column(Integer, default=20)
    max_tokens:   Mapped[int]      = mapped_column(Integer, default=500_000)
    used_queries: Mapped[int]      = mapped_column(Integer, default=0)
    used_uploads: Mapped[int]      = mapped_column(Integer, default=0)
    used_tokens:  Mapped[int]      = mapped_column(Integer, default=0)
    resets_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    user: Mapped[User] = relationship("User", back_populates="quotas")

    __table_args__ = (
        UniqueConstraint("user_id", "period", name="uq_quotas_user_period"),
    )


# ── Security/audit log ───────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id:          Mapped[str]      = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id:     Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action:      Mapped[str]      = mapped_column(String(80), nullable=False, index=True)
    target_type: Mapped[str]      = mapped_column(String(50), default="")
    target_id:   Mapped[str]      = mapped_column(String(80), default="")
    ip_address:  Mapped[str]      = mapped_column(String(45), default="")  # supports v6
    user_agent:  Mapped[str]      = mapped_column(String(300), default="")
    extra_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped[User | None] = relationship("User", foreign_keys=[user_id], back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_user_created", "user_id", "created_at"),
        Index("ix_audit_action_created", "action", "created_at"),
    )


# ── Operator-facing alerts ────────────────────────────────────────────────────

class Alert(Base):
    __tablename__ = "alerts"

    id:            Mapped[str]      = mapped_column(String(36), primary_key=True, default=_uuid)
    severity:      Mapped[AlertSeverity] = mapped_column(Enum(AlertSeverity, name="alert_severity"), nullable=False, index=True)
    source:        Mapped[str]      = mapped_column(String(50), nullable=False, index=True)
    title:         Mapped[str]      = mapped_column(String(200), nullable=False)
    body:          Mapped[str]      = mapped_column(Text, default="")
    notified_via:  Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notified_at:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    resolved_at:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
