"""Inbound email processing and polling."""

from __future__ import annotations

import asyncio
import contextlib
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
                "from_address": sender,
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
    # BUG-017: a poison message used to be retried every poll forever,
    # re-firing its workflow trigger every 30 seconds. Track per-UID failures
    # and park persistent offenders instead.
    failure_counts: dict[str, int] = {}
    max_failures = 5
    try:
        while True:
            try:
                messages = await adapter.list_messages(
                    folder=adapter.config.default_folder,
                    limit=50,
                    unread_only=True,
                )
                if messages:
                    logger.info("Email poller: %d unread message(s)", len(messages))
                for msg in messages:
                    uid = str(msg["message_id"])
                    if failure_counts.get(uid, 0) >= max_failures:
                        logger.error(
                            "Parking poison email uid=%s after %d failed attempts; "
                            "marking read to stop redelivery",
                            uid,
                            max_failures,
                        )
                        with contextlib.suppress(Exception):
                            await adapter.flag_message(uid, "read")
                        failure_counts.pop(uid, None)
                        continue
                    try:
                        full = await adapter.read_message(msg["message_id"])
                        headers = full["headers"]
                        logger.info(
                            "Processing email uid=%s from=%s subject=%s",
                            uid,
                            headers.get("from", ""),
                            headers.get("subject", ""),
                        )
                        await process_inbound_email(
                            app,
                            sender=headers.get("from", ""),
                            subject=headers.get("subject", ""),
                            body=full.get("body", ""),
                        )
                        await adapter.flag_message(msg["message_id"], "read")
                        logger.info("Marked email uid=%s as read", uid)
                        failure_counts.pop(uid, None)
                        # Brief pause between emails to avoid overwhelming
                        # downstream LLM inference with a burst of requests.
                        await asyncio.sleep(2)
                    except Exception:
                        failure_counts[uid] = failure_counts.get(uid, 0) + 1
                        logger.exception(
                            "Failed to process email uid=%s (attempt %d/%d)",
                            uid,
                            failure_counts[uid],
                            max_failures,
                        )
            except Exception:
                logger.exception("Email poll failed")
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("Email poller stopped")
        raise
