"""Inbound email processing and polling."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from hestia.email.adapter import EmailAdapter

logger = logging.getLogger(__name__)


async def process_inbound_email(
    app: Any,
    sender: str,
    subject: str,
    body: str,
) -> None:
    """Process an inbound email and publish an event to the event bus.

    Args:
        app: The application context (provides event_bus).
        sender: The email sender address.
        subject: The email subject.
        body: The plain-text body of the email.
    """
    if app.event_bus is not None:
        await app.event_bus.publish(
            "email_received",
            {
                "from": sender,
                "subject": subject,
                "body": body,
                "platform": "email",
            },
        )


async def run_email_poller(
    app: Any,
    adapter: EmailAdapter,
    interval: float = 30.0,
) -> None:
    """Background loop that polls the inbox for unread emails.

    Each unread email triggers an ``email_received`` event via the event bus,
    then is marked as read to avoid re-processing.

    Args:
        app: The application context.
        adapter: Configured EmailAdapter.
        interval: Seconds between polls (default 30).
    """
    logger.info("Email poller starting (interval=%ss)", interval)
    try:
        while True:
            try:
                messages = await adapter.list_messages(
                    folder=adapter.config.default_folder,
                    limit=50,
                    unread_only=True,
                )
                for msg in messages:
                    try:
                        full = await adapter.read_message(msg["message_id"])
                        headers = full["headers"]
                        await process_inbound_email(
                            app,
                            sender=headers.get("from", ""),
                            subject=headers.get("subject", ""),
                            body=full.get("body", ""),
                        )
                        await adapter.flag_message(msg["message_id"], "read")
                        logger.debug(
                            "Processed email from=%s subject=%s",
                            headers.get("from", ""),
                            headers.get("subject", ""),
                        )
                    except Exception:
                        logger.exception(
                            "Failed to process email uid=%s", msg["message_id"]
                        )
            except Exception:
                logger.exception("Email poll failed")
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("Email poller stopped")
        raise
