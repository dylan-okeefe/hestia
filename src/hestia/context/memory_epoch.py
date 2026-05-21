"""Memory epoch prefix builder for context injection."""

from __future__ import annotations

import logging
from datetime import timedelta

from hestia.core.clock import utcnow
from hestia.memory.store import MemoryStore

logger = logging.getLogger(__name__)


class MemoryEpochBuilder:
    """Fetches recent memories for a platform/user and formats them as a
    system-prompt prefix.
    """

    _MAX_MEMORIES = 5
    _MAX_AGE_DAYS = 30
    _MAX_CHARS = 1500

    def __init__(self, memory_store: MemoryStore) -> None:
        self._store = memory_store

    async def build_prefix(
        self, platform: str | None, platform_user: str | None
    ) -> str:
        """Build a memory epoch prefix for the given user scope.

        Args:
            platform: Platform identifier (e.g. "cli", "matrix")
            platform_user: User identifier on that platform

        Returns:
            Formatted memory prefix, or empty string if no memories exist
            or the store query fails.
        """
        try:
            memories = await self._store.list_memories(
                limit=self._MAX_MEMORIES,
                platform=platform,
                platform_user=platform_user,
            )
        except Exception:
            logger.exception("Failed to fetch memories for epoch prefix")
            return ""

        cutoff = utcnow() - timedelta(days=self._MAX_AGE_DAYS)
        recent = [m for m in memories if m.created_at >= cutoff]

        if not recent:
            return ""

        lines: list[str] = ["Relevant memories:"]
        for mem in recent:
            content = mem.content.strip()
            if mem.tags:
                tags_str = ", ".join(mem.tags)
                lines.append(f"- [{tags_str}] {content}")
            else:
                lines.append(f"- {content}")

        result = "\n".join(lines)
        if len(result) > self._MAX_CHARS:
            result = result[: self._MAX_CHARS]
        return result
