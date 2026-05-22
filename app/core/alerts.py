"""Alert notifier — Telegram-backed with DB persistence.

Severity routing:
  info     → write to alerts table only
  warn     → alerts table only
  error    → alerts table + Telegram message
  critical → alerts table + Telegram message (repeated until resolved)

Usage (async context):
    from app.core.alerts import send_alert
    await send_alert(severity="error", source="quota", title="...", body="...")

Usage (sync context, e.g. Celery tasks / Sentry before_send):
    from app.core.alerts import send_alert_sync
    send_alert_sync(severity="error", source="celery", title="...", body="...")
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def _send_telegram(text: str) -> None:
    """Fire-and-forget Telegram message. Silently fails if not configured."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        httpx.post(
            url,
            json={"chat_id": settings.telegram_chat_id, "text": text, "parse_mode": "HTML"},
            timeout=5,
        )
    except Exception as e:
        logger.warning("Telegram notify failed: %s", e)


def _format_message(severity: str, source: str, title: str, body: str) -> str:
    icons = {"info": "ℹ️", "warn": "⚠️", "error": "🔴", "critical": "🚨"}
    icon = icons.get(severity, "🔔")
    lines = [f"{icon} <b>[{severity.upper()}] {title}</b>", f"Source: {source}"]
    if body:
        lines.append(body[:500])
    return "\n".join(lines)


async def send_alert(
    severity: str,
    source: str,
    title: str,
    body: str = "",
) -> None:
    """Async version — preferred in FastAPI route context."""
    await _persist_alert(severity, source, title, body)
    if severity in ("error", "critical"):
        # Run sync Telegram call in thread pool so we don't block the event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, _send_telegram, _format_message(severity, source, title, body)
        )


def send_alert_sync(severity: str, source: str, title: str, body: str = "") -> None:
    """Sync version — use from Celery tasks, Sentry hook, health checks."""
    if severity in ("error", "critical"):
        _send_telegram(_format_message(severity, source, title, body))
    # DB persistence is best-effort from sync context
    try:
        asyncio.run(_persist_alert(severity, source, title, body))
    except Exception:
        pass  # don't raise from alert code


async def _persist_alert(severity: str, source: str, title: str, body: str) -> None:
    try:
        from app.db.base import AsyncSessionLocal
        from app.db.models import Alert, AlertSeverity
        async with AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)
            notified = None
            if severity in ("error", "critical") and settings.telegram_bot_token:
                notified = now
            alert = Alert(
                severity=AlertSeverity(severity),
                source=source,
                title=title[:200],
                body=body,
                notified_via={"telegram": True} if notified else None,
                notified_at=notified,
            )
            db.add(alert)
            await db.commit()
    except Exception as e:
        logger.warning("Failed to persist alert to DB: %s", e)
