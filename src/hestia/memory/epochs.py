"""Memory epochs - compiled snapshots of relevant memories for prompt injection.

Memory epochs are compiled once per session (at start, slot restore, or explicit
refresh) and remain stable throughout the session. This provides prefix cache
stability and predictable token budgets.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from hestia.core.clock import utcnow
from hestia.core.types import Session
from hestia.memory.store import Memory, MemoryStore


@dataclass
class MemoryEpoch:
    """A compiled snapshot of relevant memories for prompt injection."""

    compiled_text: str  # The actual text included in the system message
    created_at: datetime
    memory_count: int  # How many memories were considered
    token_estimate: int  # Approximate token count


class MemoryEpochCompiler:
    """Compiles a MemoryEpoch from the memory store.

    The epoch is a stable snapshot that gets injected into the system prompt.
    It only changes at controlled boundaries (session start, slot restore,
    explicit /refresh), not on every memory write.
    """

    def __init__(self, memory_store: MemoryStore, max_tokens: int = 500):
        """Initialize with memory store and token budget.

        Args:
            memory_store: The store to fetch memories from
            max_tokens: Maximum tokens for the compiled epoch (rough approximation)
        """
        self.store = memory_store
        self.max_tokens = max_tokens

    async def compile(self, session: Session) -> MemoryEpoch:
        """Compile a memory epoch for the given session.

        Strategy:
        1. Fetch recent memories scoped to the session user (last 30 days)
        2. Fetch tag-matched memories if session has tags
        3. Deduplicate
        4. Format as compact text block
        5. Truncate to max_tokens

        Args:
            session: The session to compile memories for

        Returns:
            A MemoryEpoch with compiled memory context scoped to the user
        """
        memories: list[Memory] = []
        seen_ids: set[str] = set()

        # 1. Fetch recent memories scoped to the session user (last 30 days)
        cutoff = utcnow() - timedelta(days=30)
        recent_memories = await self._fetch_recent_memories(
            limit=50,
            platform=session.platform,
            platform_user=session.platform_user,
        )
        for mem in recent_memories:
            if mem.created_at >= cutoff and mem.id not in seen_ids:
                memories.append(mem)
                seen_ids.add(mem.id)

        # 2. Fetch tag-matched memories if session has tags (future enhancement)
        # For now, session doesn't have tags, but we can search for common keywords
        # or use the session context to find relevant memories
        if len(memories) < 10:
            # Supplement with more recent memories if we have few
            more_memories = await self._fetch_recent_memories(
                limit=100,
                platform=session.platform,
                platform_user=session.platform_user,
            )
            for mem in more_memories:
                if mem.id not in seen_ids:
                    memories.append(mem)
                    seen_ids.add(mem.id)

        # 3. Format as compact text block
        formatted = self._format_memories(memories)

        # 4. Truncate to max_tokens (rough approximation: 4 chars per token)
        max_chars = self.max_tokens * 4
        if len(formatted) > max_chars:
            formatted = formatted[:max_chars]

        # Estimate token count
        token_estimate = len(formatted) // 4

        return MemoryEpoch(
            compiled_text=formatted,
            created_at=utcnow(),
            memory_count=len(memories),
            token_estimate=token_estimate,
        )

    async def _fetch_recent_memories(
        self,
        limit: int,
        platform: str | None = None,
        platform_user: str | None = None,
    ) -> list[Memory]:
        """Fetch the most recent memories from the store.

        Args:
            limit: Maximum number of memories to fetch
            platform: Optional platform scope
            platform_user: Optional user scope

        Returns:
            List of memories, newest first
        """
        return await self.store.list_memories(
            tag=None, limit=limit, platform=platform, platform_user=platform_user
        )

    def _format_memories(self, memories: list[Memory]) -> str:
        """Format memories as a compact text block.

        Args:
            memories: List of memories to format

        Returns:
            Formatted text suitable for prompt injection
        """
        if not memories:
            return ""

        lines: list[str] = []
        lines.append("Relevant memories:")

        for mem in memories:
            # Format: "- [tags] content" or "- content" if no tags
            content = mem.content.strip()
            if mem.tags:
                lines.append(f"- [{mem.tags}] {content}")
            else:
                lines.append(f"- {content}")

        return "\n".join(lines)

    async def compile_empty(self) -> MemoryEpoch:
        """Create an empty epoch when no memories exist.

        Returns:
            An empty MemoryEpoch
        """
        return MemoryEpoch(
            compiled_text="",
            created_at=utcnow(),
            memory_count=0,
            token_estimate=0,
        )
