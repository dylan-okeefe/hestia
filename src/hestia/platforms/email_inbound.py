"""Inbound email processing stub."""

from __future__ import annotations

from typing import Any


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
