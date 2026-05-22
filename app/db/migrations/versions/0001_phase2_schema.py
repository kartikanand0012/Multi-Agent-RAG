"""phase 2 schema — RBAC, conversations, agent runs, quotas, alerts

Revision ID: 0001_phase2_schema
Revises:
Create Date: 2026-05-22

What this does:
  - Drops legacy analytics tables (query_events, upload_events)
  - Drops users.api_key column (moves to dedicated api_keys table)
  - Adds new columns to notebooks: total_chunks, total_tokens_used, status, last_queried_at
  - Creates all new Phase 2 tables

Strategy for Postgres enums:
  Each enum is created explicitly with .create(bind, checkfirst=True) BEFORE
  the create_table call. The column definition uses create_type=False so
  SQLAlchemy does NOT try to CREATE TYPE a second time during create_table.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_phase2_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Helper: build an Enum type object for DDL creation
def _enum(*values, name: str) -> sa.Enum:
    return sa.Enum(*values, name=name)

# Helper: reference an already-created enum in a column (no auto DDL)
def _enum_col(*values, name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # ── 1. Drop legacy analytics tables ──────────────────────────────────────
    for t in ("query_events", "upload_events"):
        if t in existing_tables:
            op.drop_table(t)

    # ── 2. users table ────────────────────────────────────────────────────────
    if "users" not in existing_tables:
        op.create_table(
            "users",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("email", sa.String(255), unique=True, nullable=False),
            sa.Column("username", sa.String(50), unique=True, nullable=False),
            sa.Column("hashed_password", sa.Text, nullable=False),
            sa.Column("full_name", sa.String(120), nullable=False, server_default=""),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("is_admin", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_users_email",    "users", ["email"])
        op.create_index("ix_users_username", "users", ["username"])
        op.create_index("ix_users_is_admin", "users", ["is_admin"])
    else:
        # Drop the old api_key column if it exists
        cols = {c["name"] for c in inspector.get_columns("users")}
        if "api_key" in cols:
            with op.batch_alter_table("users") as b:
                b.drop_column("api_key")

    # ── 3. notebooks table ────────────────────────────────────────────────────
    # Create the Postgres enum type first (checkfirst so re-runs are safe)
    _enum("active", "archived", "deleting", name="notebook_status").create(bind, checkfirst=True)

    if "notebooks" not in existing_tables:
        op.create_table(
            "notebooks",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("doc_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("total_chunks", sa.Integer, nullable=False, server_default="0"),
            sa.Column("total_tokens_used", sa.Integer, nullable=False, server_default="0"),
            # create_type=False: type already created above
            sa.Column("status", _enum_col("active", "archived", "deleting", name="notebook_status"), nullable=False, server_default="active"),
            sa.Column("last_queried_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_notebooks_user_id", "notebooks", ["user_id"])
    else:
        cols = {c["name"] for c in inspector.get_columns("notebooks")}
        with op.batch_alter_table("notebooks") as b:
            if "total_chunks"      not in cols: b.add_column(sa.Column("total_chunks",      sa.Integer, nullable=False, server_default="0"))
            if "total_tokens_used" not in cols: b.add_column(sa.Column("total_tokens_used", sa.Integer, nullable=False, server_default="0"))
            if "status"            not in cols: b.add_column(sa.Column("status", _enum_col("active", "archived", "deleting", name="notebook_status"), nullable=False, server_default="active"))
            if "last_queried_at"   not in cols: b.add_column(sa.Column("last_queried_at",   sa.DateTime(timezone=True), nullable=True))

    # ── 4. RBAC ───────────────────────────────────────────────────────────────
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(50), unique=True, nullable=False),
        sa.Column("description", sa.String(255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_roles_name", "roles", ["name"])

    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(80), unique=True, nullable=False),
        sa.Column("description", sa.String(255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_permissions_code", "permissions", ["code"])

    op.create_table(
        "role_permissions",
        sa.Column("role_id",       sa.Integer,     sa.ForeignKey("roles.id",       ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_id", sa.Integer,     sa.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "user_roles",
        sa.Column("user_id",    sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_id",    sa.Integer,    sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("granted_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )

    # ── 5. api_keys ───────────────────────────────────────────────────────────
    op.create_table(
        "api_keys",
        sa.Column("id",           sa.String(36), primary_key=True),
        sa.Column("user_id",      sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key_hash",     sa.String(64), unique=True, nullable=False),
        sa.Column("label",        sa.String(80), nullable=False, server_default=""),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at",   sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at",   sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at",   sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_api_keys_user_id",  "api_keys", ["user_id"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])

    # ── 6. conversations ──────────────────────────────────────────────────────
    op.create_table(
        "conversations",
        sa.Column("id",              sa.String(36), primary_key=True),
        sa.Column("user_id",         sa.String(36), sa.ForeignKey("users.id",      ondelete="CASCADE"), nullable=False),
        sa.Column("notebook_id",     sa.String(64), sa.ForeignKey("notebooks.id",  ondelete="CASCADE"), nullable=False),
        sa.Column("title",           sa.String(200), nullable=False, server_default="New conversation"),
        sa.Column("message_count",   sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at",      sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at",      sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_conversations_user_id",      "conversations", ["user_id"])
    op.create_index("ix_conversations_notebook_id",  "conversations", ["notebook_id"])
    op.create_index("ix_conversations_user_created", "conversations", ["user_id", "created_at"])

    # ── 7. agent_runs ─────────────────────────────────────────────────────────
    _enum("pending", "running", "done", "failed", name="run_status").create(bind, checkfirst=True)
    op.create_table(
        "agent_runs",
        sa.Column("id",                  sa.String(36), primary_key=True),
        sa.Column("user_id",             sa.String(36), sa.ForeignKey("users.id",     ondelete="CASCADE"), nullable=False),
        sa.Column("notebook_id",         sa.String(64), sa.ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("query_text",          sa.Text, nullable=False),
        sa.Column("intent_type",         sa.String(50), nullable=False, server_default="unknown"),
        sa.Column("sub_queries",         sa.JSON, nullable=True),
        sa.Column("retry_count",         sa.Integer, nullable=False, server_default="0"),
        sa.Column("sources_found",       sa.Integer, nullable=False, server_default="0"),
        sa.Column("validation_passed",   sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("unsupported_claims",  sa.JSON, nullable=True),
        sa.Column("validation_feedback", sa.Text, nullable=False, server_default=""),
        sa.Column("total_tokens_in",     sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_tokens_out",    sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_cost_usd",      sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("latency_ms",          sa.Integer, nullable=False, server_default="0"),
        sa.Column("langfuse_trace_id",   sa.String(64), nullable=True),
        sa.Column("status",              _enum_col("pending", "running", "done", "failed", name="run_status"), nullable=False, server_default="pending"),
        sa.Column("error",               sa.Text, nullable=False, server_default=""),
        sa.Column("cached",              sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("model_strong",        sa.String(50), nullable=False, server_default=""),
        sa.Column("model_fast",          sa.String(50), nullable=False, server_default=""),
        sa.Column("created_at",          sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at",         sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_runs_user_id",        "agent_runs", ["user_id"])
    op.create_index("ix_agent_runs_notebook_id",    "agent_runs", ["notebook_id"])
    op.create_index("ix_agent_runs_status",         "agent_runs", ["status"])
    op.create_index("ix_agent_runs_langfuse_trace", "agent_runs", ["langfuse_trace_id"])
    op.create_index("ix_agent_runs_user_created",   "agent_runs", ["user_id", "created_at"])
    op.create_index("ix_agent_runs_status_created", "agent_runs", ["status", "created_at"])

    # ── 8. messages ───────────────────────────────────────────────────────────
    _enum("user", "assistant", "system", name="message_role").create(bind, checkfirst=True)
    op.create_table(
        "messages",
        sa.Column("id",              sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role",            _enum_col("user", "assistant", "system", name="message_role"), nullable=False),
        sa.Column("content",         sa.Text, nullable=False),
        sa.Column("agent_run_id",    sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at",      sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_conv_created",    "messages", ["conversation_id", "created_at"])

    # ── 9. agent_steps ───────────────────────────────────────────────────────
    _enum("intent", "retrieval", "reasoning", "validation", name="agent_name").create(bind, checkfirst=True)
    op.create_table(
        "agent_steps",
        sa.Column("id",             sa.String(36), primary_key=True),
        sa.Column("agent_run_id",   sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_name",     _enum_col("intent", "retrieval", "reasoning", "validation", name="agent_name"), nullable=False),
        sa.Column("step_order",     sa.Integer, nullable=False, server_default="0"),
        sa.Column("input_summary",  sa.Text, nullable=False, server_default=""),
        sa.Column("output_summary", sa.Text, nullable=False, server_default=""),
        sa.Column("tokens_in",      sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_out",     sa.Integer, nullable=False, server_default="0"),
        sa.Column("latency_ms",     sa.Integer, nullable=False, server_default="0"),
        sa.Column("error",          sa.Text, nullable=False, server_default=""),
        sa.Column("extra_metadata", sa.JSON, nullable=True),
        sa.Column("created_at",     sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agent_steps_run_id", "agent_steps", ["agent_run_id"])

    # ── 10. retrieved_chunks ──────────────────────────────────────────────────
    op.create_table(
        "retrieved_chunks",
        sa.Column("id",                 sa.String(36), primary_key=True),
        sa.Column("agent_run_id",       sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id",           sa.String(80), nullable=False),
        sa.Column("chunk_text_preview", sa.Text, nullable=False, server_default=""),
        sa.Column("score",              sa.Numeric(8, 6), nullable=False, server_default="0"),
        sa.Column("layer",              sa.Integer, nullable=False, server_default="0"),
        sa.Column("source",             sa.String(500), nullable=False, server_default=""),
        sa.Column("rank_position",      sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_retrieved_chunks_run_id", "retrieved_chunks", ["agent_run_id"])

    # ── 11. ingestion_jobs ────────────────────────────────────────────────────
    _enum("queued", "processing", "done", "failed", name="job_status").create(bind, checkfirst=True)
    op.create_table(
        "ingestion_jobs",
        sa.Column("id",                sa.String(36), primary_key=True),
        sa.Column("user_id",           sa.String(36), sa.ForeignKey("users.id",     ondelete="CASCADE"), nullable=False),
        sa.Column("notebook_id",       sa.String(64), sa.ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("file_size_bytes",   sa.Integer, nullable=False, server_default="0"),
        sa.Column("status",            _enum_col("queued", "processing", "done", "failed", name="job_status"), nullable=False, server_default="queued"),
        sa.Column("use_raptor",        sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("total_nodes",       sa.Integer, nullable=False, server_default="0"),
        sa.Column("leaf_chunks",       sa.Integer, nullable=False, server_default="0"),
        sa.Column("processing_ms",     sa.Integer, nullable=False, server_default="0"),
        sa.Column("celery_task_id",    sa.String(80), nullable=True),
        sa.Column("error",             sa.Text, nullable=False, server_default=""),
        sa.Column("queued_at",         sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at",        sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at",       sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ingestion_jobs_user_id",     "ingestion_jobs", ["user_id"])
    op.create_index("ix_ingestion_jobs_notebook_id", "ingestion_jobs", ["notebook_id"])
    op.create_index("ix_ingestion_jobs_status",      "ingestion_jobs", ["status"])
    op.create_index("ix_ingestion_jobs_task_id",     "ingestion_jobs", ["celery_task_id"])

    # ── 12. usage_events ──────────────────────────────────────────────────────
    _enum("query", "upload", "embedding", name="usage_event_type").create(bind, checkfirst=True)
    op.create_table(
        "usage_events",
        sa.Column("id",               sa.String(36), primary_key=True),
        sa.Column("user_id",          sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type",       _enum_col("query", "upload", "embedding", name="usage_event_type"), nullable=False),
        sa.Column("agent_run_id",     sa.String(36), sa.ForeignKey("agent_runs.id",     ondelete="SET NULL"), nullable=True),
        sa.Column("ingestion_job_id", sa.String(36), sa.ForeignKey("ingestion_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tokens_in",        sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_out",       sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd",         sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("created_at",       sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_usage_user_id",      "usage_events", ["user_id"])
    op.create_index("ix_usage_user_created", "usage_events", ["user_id", "created_at"])
    op.create_index("ix_usage_type_created", "usage_events", ["event_type", "created_at"])

    # ── 13. quotas ────────────────────────────────────────────────────────────
    _enum("daily", "monthly", name="quota_period").create(bind, checkfirst=True)
    op.create_table(
        "quotas",
        sa.Column("id",           sa.String(36), primary_key=True),
        sa.Column("user_id",      sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period",       _enum_col("daily", "monthly", name="quota_period"), nullable=False, server_default="daily"),
        sa.Column("max_queries",  sa.Integer, nullable=False, server_default="200"),
        sa.Column("max_uploads",  sa.Integer, nullable=False, server_default="20"),
        sa.Column("max_tokens",   sa.Integer, nullable=False, server_default="500000"),
        sa.Column("used_queries", sa.Integer, nullable=False, server_default="0"),
        sa.Column("used_uploads", sa.Integer, nullable=False, server_default="0"),
        sa.Column("used_tokens",  sa.Integer, nullable=False, server_default="0"),
        sa.Column("resets_at",    sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at",   sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at",   sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "period", name="uq_quotas_user_period"),
    )
    op.create_index("ix_quotas_user_id", "quotas", ["user_id"])

    # ── 14. audit_logs ────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id",             sa.String(36), primary_key=True),
        sa.Column("user_id",        sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action",         sa.String(80), nullable=False),
        sa.Column("target_type",    sa.String(50), nullable=False, server_default=""),
        sa.Column("target_id",      sa.String(80), nullable=False, server_default=""),
        sa.Column("ip_address",     sa.String(45), nullable=False, server_default=""),
        sa.Column("user_agent",     sa.String(300), nullable=False, server_default=""),
        sa.Column("extra_metadata", sa.JSON, nullable=True),
        sa.Column("created_at",     sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_user_id",        "audit_logs", ["user_id"])
    op.create_index("ix_audit_action",         "audit_logs", ["action"])
    op.create_index("ix_audit_user_created",   "audit_logs", ["user_id", "created_at"])
    op.create_index("ix_audit_action_created", "audit_logs", ["action", "created_at"])

    # ── 15. alerts ────────────────────────────────────────────────────────────
    _enum("info", "warn", "error", "critical", name="alert_severity").create(bind, checkfirst=True)
    op.create_table(
        "alerts",
        sa.Column("id",           sa.String(36), primary_key=True),
        sa.Column("severity",     _enum_col("info", "warn", "error", "critical", name="alert_severity"), nullable=False),
        sa.Column("source",       sa.String(50), nullable=False),
        sa.Column("title",        sa.String(200), nullable=False),
        sa.Column("body",         sa.Text, nullable=False, server_default=""),
        sa.Column("notified_via", sa.JSON, nullable=True),
        sa.Column("notified_at",  sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at",   sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at",  sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_alerts_severity",   "alerts", ["severity"])
    op.create_index("ix_alerts_source",     "alerts", ["source"])
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()

    # Drop tables in reverse FK order
    for t in ("alerts", "audit_logs", "quotas", "usage_events", "ingestion_jobs",
              "retrieved_chunks", "agent_steps", "messages", "agent_runs",
              "conversations", "api_keys", "user_roles", "role_permissions",
              "permissions", "roles"):
        op.drop_table(t)

    # Drop Postgres enum types
    for name in ("alert_severity", "quota_period", "usage_event_type", "job_status",
                 "agent_name", "message_role", "run_status", "notebook_status"):
        sa.Enum(name=name).drop(bind, checkfirst=True)
