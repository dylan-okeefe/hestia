"""Shared confirmation infrastructure for platform adapters.

Provides in-memory confirmation request tracking and a helper to render
tool arguments for human review. Upgrade path: replace ConfirmationStore
with a persistent backend (Redis, DB) for multi-process deployments.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

MAX_ARG_LEN = 200


@dataclass
class ConfirmationRequest:
    """A single confirmation request waiting for operator response."""

    id: str
    tool_name: str
    arguments: dict[str, Any]
    prompt: str
    created_at: datetime
    expires_at: datetime
    future: asyncio.Future[bool] | None = None


class ConfirmationStore:
    """In-memory store for pending confirmation requests.

    Each request is keyed by a UUID and backed by an ``asyncio.Future`` so
    the caller can ``await`` the operator's response (or timeout).

    Upgrade path: swap this class for a persistent store that serialises
    ``ConfirmationRequest`` to Redis / DB and restores the future on load.
    """

    def __init__(self) -> None:
        self._pending: dict[str, ConfirmationRequest] = {}

    def create(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_seconds: float = 60.0,
    ) -> ConfirmationRequest:
        """Create a new pending confirmation request.

        Args:
            tool_name: Name of the tool awaiting approval.
            arguments: Arguments the tool intends to run with.
            timeout_seconds: How long the request remains valid.

        Returns:
            The created ``ConfirmationRequest`` (await ``request.future``).
        """
        now = datetime.now(timezone.utc)
        req = ConfirmationRequest(
            id=str(uuid.uuid4()),
            tool_name=tool_name,
            arguments=arguments,
            prompt=render_args_for_human_review(tool_name, arguments),
            created_at=now,
            expires_at=now + timedelta(seconds=timeout_seconds),
            future=asyncio.get_running_loop().create_future(),
        )
        self._pending[req.id] = req
        return req

    def get(self, request_id: str) -> ConfirmationRequest | None:
        """Return a pending request, or ``None`` if absent / expired."""
        self._gc()
        return self._pending.get(request_id)

    def resolve(self, request_id: str, approved: bool) -> bool:
        """Resolve a pending request.

        Returns:
            ``True`` if the request existed and was resolved, ``False`` otherwise.
        """
        req = self._pending.pop(request_id, None)
        if req is not None and req.future is not None and not req.future.done():
            req.future.set_result(approved)
            return True
        return False

    def cancel(self, request_id: str) -> bool:
        """Cancel a pending request (treats as denied).

        Returns:
            ``True`` if the request existed and was cancelled, ``False`` otherwise.
        """
        return self.resolve(request_id, False)

    def _gc(self) -> None:
        """Remove expired, unresolved requests and fail their futures."""
        now = datetime.now(timezone.utc)
        expired = [
            rid
            for rid, req in self._pending.items()
            if req.future is not None and req.expires_at < now and not req.future.done()
        ]
        for rid in expired:
            req = self._pending.pop(rid)
            if req.future is not None and not req.future.done():
                req.future.set_result(False)

    def __len__(self) -> int:
        self._gc()
        return len(self._pending)


def render_args_for_human_review(tool_name: str, arguments: dict[str, Any]) -> str:
    """Render tool arguments as a short, human-readable JSON snippet.

    Long fields (> ``MAX_ARG_LEN`` chars) are truncated with ``...``.
    """
    truncated: dict[str, Any] = {}
    for key, value in arguments.items():
        if isinstance(value, str):
            text = value
        else:
            text = json.dumps(value)
        if len(text) > MAX_ARG_LEN:
            text = text[:MAX_ARG_LEN] + "..."
        truncated[key] = text
    return json.dumps(truncated, indent=2)
