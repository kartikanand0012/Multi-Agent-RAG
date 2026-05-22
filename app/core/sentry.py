"""Sentry SDK initialisation — backend only.

Imported once at app startup (main.py). No-ops when SENTRY_DSN is missing or
when not in production so dev/test runs stay clean.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def init_sentry() -> None:
    from app.core.config import settings

    if not settings.sentry_enabled:
        logger.info("Sentry not enabled (check SENTRY_DSN + ENVIRONMENT=production)")
        return

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[
            FastApiIntegration(transaction_style="url"),
            SqlalchemyIntegration(),
            CeleryIntegration(),
        ],
        traces_sample_rate=settings.sentry_traces_sample_rate,
        environment=settings.environment,
        # Don't include request body in events (PII concern)
        send_default_pii=False,
        before_send=_before_send,
    )
    logger.info("Sentry initialised (DSN configured, environment=%s)", settings.environment)


def _before_send(event: dict, hint: dict) -> dict | None:
    """Send critical/error events to Telegram before forwarding to Sentry."""
    level = event.get("level", "")
    if level in ("error", "fatal"):
        try:
            from app.core.alerts import send_alert_sync
            title = event.get("exception", {}).get("values", [{}])[0].get("type", "Error")
            value = event.get("exception", {}).get("values", [{}])[0].get("value", "")
            send_alert_sync(
                severity="error",
                source="sentry",
                title=f"{title}: {value[:80]}",
                body=f"Sentry event_id={event.get('event_id', 'unknown')}",
            )
        except Exception:
            pass  # never block Sentry from sending the event
    return event
