"""Shared response infrastructure for interactive workflow nodes.

Provides in-memory response request tracking so workflow nodes can await
user replies from platform adapters. Upgrade path: replace with a persistent
backend (Redis, DB) for multi-process deployments.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


@dataclass
class WorkflowResponseRequest:
    """A single workflow response request waiting for user input."""

    id: str
    platform: str
    platform_user: str
    created_at: datetime
    future: asyncio.Future[str]


class WorkflowResponseStore:
    """In-memory store for pending workflow response requests.

    Each request is keyed by a UUID and backed by an ``asyncio.Future`` so
    the caller can ``await`` the user's response (or timeout).
    """

    def __init__(self) -> None:
        self._pending: dict[str, WorkflowResponseRequest] = {}

    def create(
        self, platform: str, platform_user: str
    ) -> tuple[str, asyncio.Future[str]]:
        """Create a new pending response request.

        Returns:
            Tuple of (request_id, future).
        """
        now = datetime.now(UTC)
        req_id = str(uuid.uuid4())
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        req = WorkflowResponseRequest(
            id=req_id,
            platform=platform,
            platform_user=platform_user,
            created_at=now,
            future=future,
        )
        self._pending[req_id] = req
        return req_id, future

    def resolve(self, request_id: str, response: str) -> bool:
        """Resolve a pending request with a user response.

        Returns:
            ``True`` if the request existed and was resolved, ``False`` otherwise.
        """
        req = self._pending.pop(request_id, None)
        if req is not None and not req.future.done():
            req.future.set_result(response)
            return True
        return False

    def cancel(self, request_id: str) -> bool:
        """Cancel a pending request (treats as timeout).

        Returns:
            ``True`` if the request existed and was cancelled, ``False`` otherwise.
        """
        req = self._pending.pop(request_id, None)
        if req is not None and not req.future.done():
            req.future.cancel()
            return True
        return False

    def find_pending(self, platform: str, platform_user: str) -> str | None:
        """Find a pending request ID for the given platform and user."""
        for req_id, req in self._pending.items():
            if req.platform == platform and req.platform_user == platform_user:
                return req_id
        return None

    def __len__(self) -> int:
        return len(self._pending)


# Module-level singleton shared by platform adapters and workflow nodes.
DEFAULT_RESPONSE_STORE = WorkflowResponseStore()
