"""phase 2 schema — RBAC, conversations, agent runs, quotas, alerts

Revision ID: 0001_phase2_schema
Revises:
Create Date: 2026-05-22

What this does:
  - Drops legacy analytics tables (query_events, upload_events) — superseded by
    agent_runs + agent_steps + usage_events. Old user/notebook data is preserved.
  - Drops users.api_key (moves to dedicated api_keys table; existing users will
    need to regenerate via POST /auth/me/api-keys).
  - Adds new columns to notebooks: total_chunks, total_tokens_used, status,
    last_queried_at.
  - Creates all new Phase 2 tables.

Safe to run on both:
  - fresh preprod DB (just creates)
  - existing prod DB with users + notebooks (preserves them, drops only analytics)
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_phase2_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── enum types (created at module level so we can refer to them by name) ──────
notebook_status = sa.Enum("active", "archived", "deleting", name="notebook_status")
message_role    = sa.Enum("user", "assistant", "system", name="message_role")
agent_name      = sa.Enum("intent", "retrieval", "reasoning", "validation", name="agent_name")
run_status      = sa.Enum("pending", "running", "done", "failed", name="run_status")
job_status      = sa.Enum("queued", "processing", "done", "failed", name="job_status")
usage_event_type = sa.Enum("query", "upload", "embedding", name="usage_event_type")
quota_period    = sa.Enum("daily", "monthly", name="quota_period")
alert_severity  = sa.Enum("info", "warn", "error", "critical", name="alert_severity")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # ── 1. Drop legacy analytics (idempotent) ─────────────────────────────────
    if "query_events" in existing_tables:
        op.drop_table("query_events")
    if "upload_events" in existing_tables:
        op.drop_table("upload_events")

    # ── 2. Adjust users (drop api_key column if present) ──────────────────────
    if "users" in existing_tables:
        cols = {c["name"] for c in inspector.get_columns("users")}
        if "api_key" in cols:
            with op.batch_alter_table("users") as b:
                b.drop_column("api_key")
    else:
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

    # ── 3. Notebooks: ensure exists + add new columns ─────────────────────────
    if "notebooks" not in existing_tables:
        notebook_status.create(bind, checkfirst=True)
        op.create_table(
            "notebooks",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("doc_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("total_chunks", sa.Integer, nullable=False, server_default="0"),
            sa.Column("total_tokens_used", sa.Integer, nullable=False, server_default="0"),
            sa.Column("status", notebook_status, nullable=False, server_default="active"),
            sa.Column("last_queried_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_notebooks_user_id", "notebooks", ["user_id"])
    else:
        notebook_status.create(bind, checkfirst=True)
        cols = {c["name"] for c in inspector.get_columns("notebooks")}
        with op.batch_alter_table("notebooks") as b:
            if "total_chunks" not in cols:
                b.add_column(sa.Column("total_chunks", sa.Integer, nullable=False, server_default="0"))
            if "total_tokens_used" not in cols:
                b.add_column(sa.Column("total_tokens_used", sa.Integer, nullable=False, server_default="0"))
            if "status" not in cols:
                b.add_column(sa.Column("status", notebook_status, nullable=False, server_default="active"))
            if "last_queried_at" not in cols:
                b.add_column(sa.Column("last_queried_at", sa.DateTime(timezone=True), nullable=True))

    # ── 4. RBAC tables ────────────────────────────────────────────────────────
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
        sa.Column("role_id", sa.Integer, sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_id", sa.Integer, sa.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_id", sa.Integer, sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("granted_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )

    # ── 5. API keys ───────────────────────────────────────────────────────────
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("label", sa.String(80), nullable=False, server_default=""),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_api_keys_user_id",  "api_keys", ["user_id"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])

    # ── 6. Conversation thread ────────────────────────────────────────────────
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("notebook_id", sa.String(64), sa.ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False, server_default="New conversation"),
        sa.Column("message_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_conversations_user_id",      "conversations", ["user_id"])
    op.create_index("ix_conversations_notebook_id",  "conversations", ["notebook_id"])
    op.create_index("ix_conversations_user_created", "conversations", ["user_id", "created_at"])

    # ── 7. agent_runs (created BEFORE messages because messages.agent_run_id FKs it) ──
    run_status.create(bind, checkfirst=True)
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("notebook_id", sa.String(64), sa.ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("query_text", sa.Text, nullable=False),
        sa.Column("intent_type", sa.String(50), nullable=False, server_default="unknown"),
        sa.Column("sub_queries", sa.JSON, nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sources_found", sa.Integer, nullable=False, server_default="0"),
        sa.Column("validation_passed", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("unsupported_claims", sa.JSON, nullable=True),
        sa.Column("validation_feedback", sa.Text, nullable=False, server_default=""),
        sa.Column("total_tokens_in", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_tokens_out", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_cost_usd", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("langfuse_trace_id", sa.String(64), nullable=True),
        sa.Column("status", run_status, nullable=False, server_default="pending"),
        sa.Column("error", sa.Text, nullable=False, server_default=""),
        sa.Column("cached", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("model_strong", sa.String(50), nullable=False, server_default=""),
        sa.Column("model_fast",   sa.String(50), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_runs_user_id",          "agent_runs", ["user_id"])
    op.create_index("ix_agent_runs_notebook_id",      "agent_runs", ["notebook_id"])
    op.create_index("ix_agent_runs_status",           "agent_runs", ["status"])
    op.create_index("ix_agent_runs_langfuse_trace",   "agent_runs", ["langfuse_trace_id"])
    op.create_index("ix_agent_runs_user_created",     "agent_runs", ["user_id", "created_at"])
    op.create_index("ix_agent_runs_status_created",   "agent_runs", ["status", "created_at"])

    # ── 8. messages (FKs agent_runs) ──────────────────────────────────────────
    message_role.create(bind, checkfirst=True)
    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", message_role, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("agent_run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_conv_created",    "messages", ["conversation_id", "created_at"])

    # ── 9. agent_steps + retrieved_chunks ─────────────────────────────────────
    agent_name.create(bind, checkfirst=True)
    op.create_table(
        "agent_steps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_name", agent_name, nullable=False),
        sa.Column("step_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("input_summary", sa.Text, nullable=False, server_default=""),
        sa.Column("output_summary", sa.Text, nullable=False, server_default=""),
        sa.Column("tokens_in", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer, nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text, nullable=False, server_default=""),
        sa.Column("extra_metadata", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agent_steps_run_id", "agent_steps", ["agent_run_id"])

    op.create_table(
        "retrieved_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id", sa.String(80), nullable=False),
        sa.Column("chunk_text_preview", sa.Text, nullable=False, server_default=""),
        sa.Column("score", sa.Numeric(8, 6), nullable=False, server_default="0"),
        sa.Column("layer", sa.Integer, nullable=False, server_default="0"),
        sa.Column("source", sa.String(500), nullable=False, server_default=""),
        sa.Column("rank_position", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_retrieved_chunks_run_id", "retrieved_chunks", ["agent_run_id"])

    # ── 10. ingestion_jobs ────────────────────────────────────────────────────
    job_status.create(bind, checkfirst=True)
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("notebook_id", sa.String(64), sa.ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("file_size_bytes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", job_status, nullable=False, server_default="queued"),
        sa.Column("use_raptor", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("total_nodes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("leaf_chunks", sa.Integer, nullable=False, server_default="0"),
        sa.Column("processing_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("celery_task_id", sa.String(80), nullable=True),
        sa.Column("error", sa.Text, nullable=False, server_default=""),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ingestion_jobs_user_id",     "ingestion_jobs", ["user_id"])
    op.create_index("ix_ingestion_jobs_notebook_id", "ingestion_jobs", ["notebook_id"])
    op.create_index("ix_ingestion_jobs_status",      "ingestion_jobs", ["status"])
    op.create_index("ix_ingestion_jobs_task_id",     "ingestion_jobs", ["celery_task_id"])

    # ── 11. usage_events ──────────────────────────────────────────────────────
    usage_event_type.create(bind, checkfirst=True)
    op.create_table(
        "usage_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", usage_event_type, nullable=False),
        sa.Column("agent_run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ingestion_job_id", sa.String(36), sa.ForeignKey("ingestion_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tokens_in", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_usage_user_id",      "usage_events", ["user_id"])
    op.create_index("ix_usage_user_created", "usage_events", ["user_id", "created_at"])
    op.create_index("ix_usage_type_created", "usage_events", ["event_type", "created_at"])

    # ── 12. quotas ────────────────────────────────────────────────────────────
    quota_period.create(bind, checkfirst=True)
    op.create_table(
        "quotas",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period", quota_period, nullable=False, server_default="daily"),
        sa.Column("max_queries", sa.Integer, nullable=False, server_default="200"),
        sa.Column("max_uploads", sa.Integer, nullable=False, server_default="20"),
        sa.Column("max_tokens",  sa.Integer, nullable=False, server_default="500000"),
        sa.Column("used_queries", sa.Integer, nullable=False, server_default="0"),
        sa.Column("used_uploads", sa.Integer, nullable=False, server_default="0"),
        sa.Column("used_tokens",  sa.Integer, nullable=False, server_default="0"),
        sa.Column("resets_at",  sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "period", name="uq_quotas_user_period"),
    )
    op.create_index("ix_quotas_user_id", "quotas", ["user_id"])

    # ── 13. audit_logs ────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=False, server_default=""),
        sa.Column("target_id", sa.String(80), nullable=False, server_default=""),
        sa.Column("ip_address", sa.String(45), nullable=False, server_default=""),
        sa.Column("user_agent", sa.String(300), nullable=False, server_default=""),
        sa.Column("extra_metadata", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_user_id",        "audit_logs", ["user_id"])
    op.create_index("ix_audit_action",         "audit_logs", ["action"])
    op.create_index("ix_audit_user_created",   "audit_logs", ["user_id", "created_at"])
    op.create_index("ix_audit_action_created", "audit_logs", ["action", "created_at"])

    # ── 14. alerts ────────────────────────────────────────────────────────────
    alert_severity.create(bind, checkfirst=True)
    op.create_table(
        "alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("severity", alert_severity, nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text, nullable=False, server_default=""),
        sa.Column("notified_via", sa.JSON, nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_alerts_severity",   "alerts", ["severity"])
    op.create_index("ix_alerts_source",     "alerts", ["source"])
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"])


def downgrade() -> None:
    # Reverse order — drop dependents first
    op.drop_table("alerts")
    op.drop_table("audit_logs")
    op.drop_table("quotas")
    op.drop_table("usage_events")
    op.drop_table("ingestion_jobs")
    op.drop_table("retrieved_chunks")
    op.drop_table("agent_steps")
    op.drop_table("messages")
    op.drop_table("agent_runs")
    op.drop_table("conversations")
    op.drop_table("api_keys")
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")

    bind = op.get_bind()
    for e in (alert_severity, quota_period, usage_event_type, job_status,
              agent_name, message_role, run_status, notebook_status):
        e.drop(bind, checkfirst=True)
