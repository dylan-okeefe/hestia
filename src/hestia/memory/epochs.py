"""Memory epochs - compiled snapshots of relevant memories for prompt injection.

Memory epochs are compiled once per session (at start, slot restore, or explicit
refresh) and remain stable throughout the session. This provides prefix cache
stability and predictable token budgets.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

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

    def __init__(
        self,
        memory_store: MemoryStore,
        max_tokens: int = 500,
        global_cap_ratio: float = 0.3,
    ):
        """Initialize with memory store and token budget.

        Args:
            memory_store: The store to fetch memories from
            max_tokens: Maximum tokens for the compiled epoch (rough approximation)
            global_cap_ratio: Soft cap for global memories as a fraction of
                ``max_tokens``. Default 0.3 (30%).
        """
        self.store = memory_store
        self.max_tokens = max_tokens
        self.global_cap_ratio = global_cap_ratio

    async def compile(
        self,
        session: Session,
        topic_ids: list[str] | None = None,
        active_sender_platform_user: str | None = None,
    ) -> MemoryEpoch:
        """Compile a memory epoch for the given session.

        Strategy:
        1. Fetch global memories first, up to the configured soft cap.
        2. Fill the remainder with subscribed-topic memories, merged by recency.
        3. Slack flows down: a small global pool leaves more room for topics.
        4. Truncate to max_tokens.

        Args:
            session: The session to compile memories for
            topic_ids: Subscribed topic IDs. None/empty means no topic memories.
            active_sender_platform_user: For group chats, the active sender whose
                global memories should be used. Defaults to ``session.platform_user``.

        Returns:
            A MemoryEpoch with compiled memory context scoped to the user/room.
        """
        global_memories, topic_memories = await self.store.get_for_epoch(
            platform=session.platform,
            platform_user=session.platform_user,
            topic_ids=topic_ids or [],
            active_sender_platform_user=active_sender_platform_user,
        )

        # Sort key seam: recency now, importance later.
        def _sort_key(mem: Memory) -> datetime:
            return mem.created_at

        global_memories = sorted(global_memories, key=_sort_key, reverse=True)
        topic_memories = sorted(topic_memories, key=_sort_key, reverse=True)

        global_cap_tokens = int(self.max_tokens * self.global_cap_ratio)

        selected: list[Memory] = []
        seen_ids: set[str] = set()
        used_tokens = 0

        # 1. Global memories first, up to the soft cap.
        for mem in global_memories:
            if mem.id in seen_ids:
                continue
            mem_tokens = self._estimate_memory_tokens(mem)
            if used_tokens + mem_tokens > global_cap_tokens:
                break
            selected.append(mem)
            seen_ids.add(mem.id)
            used_tokens += mem_tokens

        # 2. Topic memories fill the remainder. Slack flows down automatically
        # because the loop stops when the total budget is exhausted.
        for mem in topic_memories:
            if mem.id in seen_ids:
                continue
            mem_tokens = self._estimate_memory_tokens(mem)
            if used_tokens + mem_tokens > self.max_tokens:
                break
            selected.append(mem)
            seen_ids.add(mem.id)
            used_tokens += mem_tokens

        # 3. Format and truncate to budget.
        formatted = self._format_memories(selected)
        max_chars = self.max_tokens * 4
        if len(formatted) > max_chars:
            formatted = formatted[:max_chars]

        token_estimate = len(formatted) // 4

        return MemoryEpoch(
            compiled_text=formatted,
            created_at=utcnow(),
            memory_count=len(selected),
            token_estimate=token_estimate,
        )

    def _estimate_memory_tokens(self, mem: Memory) -> int:
        """Rough per-memory token estimate for budget accounting."""
        line = self._format_memory(mem)
        return max(1, len(line) // 4)

    def _format_memory(self, mem: Memory) -> str:
        """Format a single memory as a bullet line."""
        content = mem.content.strip()
        if mem.tags:
            tags_str = ", ".join(mem.tags)
            return f"- [{tags_str}] {content}"
        return f"- {content}"

    def _format_memories(self, memories: list[Memory]) -> str:
        """Format memories as a compact text block.

        Args:
            memories: List of memories to format

        Returns:
            Formatted text suitable for prompt injection
        """
        if not memories:
            return ""

        lines: list[str] = ["Relevant memories:"]
        for mem in memories:
            lines.append(self._format_memory(mem))

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
