"""Core types for skill execution."""

from dataclasses import dataclass, field
from typing import Any, cast


@dataclass
class SkillResult:
    """Result of a skill execution."""

    summary: str
    status: str = "success"  # "success", "partial", "failed"
    artifacts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillContext:
    """Context passed to skill functions during execution.

    Provides access to tool calls, memory, and other Hestia capabilities
    without exposing the full internal state.
    """

    session_id: str
    user_input: str
    _tool_caller: Any = field(repr=False, default=None)
    _memory_store: Any = field(repr=False, default=None)

    async def call_tool(self, name: str, **arguments: Any) -> Any:
        """Call a tool by name with arguments.

        Args:
            name: Tool name
            **arguments: Tool arguments

        Returns:
            Tool result

        Raises:
            RuntimeError: If no tool caller is configured
        """
        if self._tool_caller is None:
            raise RuntimeError("No tool caller configured in skill context")
        result = await self._tool_caller(name, arguments)
        return result

    async def search_memory(self, query: str, limit: int = 5) -> list[Any]:
        """Search memories.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of memory results

        Raises:
            RuntimeError: If no memory store is configured
        """
        if self._memory_store is None:
            raise RuntimeError("No memory store configured in skill context")
        return cast("list[Any]", await self._memory_store.search(query, limit=limit))

    async def save_memory(self, content: str, tags: list[str] | None = None) -> Any:
        """Save a memory.

        Args:
            content: Memory content
            tags: Optional tags

        Returns:
            Saved memory

        Raises:
            RuntimeError: If no memory store is configured
        """
        if self._memory_store is None:
            raise RuntimeError("No memory store configured in skill context")
        return await self._memory_store.save(content=content, tags=tags or [])
