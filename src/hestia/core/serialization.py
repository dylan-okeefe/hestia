"""Serialization utilities for Hestia core types."""

from __future__ import annotations

import json
from typing import Any

from hestia.core.types import Message


def message_to_dict(msg: Message) -> dict[str, Any]:
    """Convert a Message to an OpenAI-compatible dict."""
    result: dict[str, Any] = {
        "role": msg.role,
        "content": msg.content,
    }

    if msg.tool_calls:
        result["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments),
                },
            }
            for tc in msg.tool_calls
        ]

    if msg.tool_call_id:
        result["tool_call_id"] = msg.tool_call_id

    # Note: We intentionally do NOT include reasoning_content here.
    # It gets stripped before sending.

    return result
