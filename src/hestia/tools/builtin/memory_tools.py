"""Memory tools — search and save to long-term memory."""

from collections.abc import Callable, Coroutine
from typing import Any, cast

from hestia.memory.store import MemoryStore
from hestia.runtime_context import (
    current_platform,
    current_platform_user,
    current_session_id,
)
from hestia.tools.capabilities import MEMORY_READ, MEMORY_WRITE
from hestia.tools.metadata import tool


def make_search_memory_tool(
    memory_store: MemoryStore,
) -> Callable[..., Coroutine[Any, Any, str]]:
    """Create a search_memory tool bound to a MemoryStore instance."""

    @tool(
        name="search_memory",
        public_description="Search long-term memory. Params: query (str), limit (int, default 5).",

        tags=["memory", "builtin"],
        capabilities=[MEMORY_READ],
    )
    async def search_memory(query: str, limit: int = 5) -> str:
        """Search long-term memory using full-text search.

        Args:
            query: Search query (supports AND, OR, NOT, "exact phrases")
            limit: Maximum number of results (default 5)

        Returns:
            Formatted list of matching memories with IDs, tags, and dates.
        """
        # Scope to current user identity (set by orchestrator in process_turn)
        results = await memory_store.search(query, limit=limit)
        if not results:
            return "No memories found matching your query."

        lines = []
        for mem in results:
            tags_str = ", ".join(mem.tags) if mem.tags else ""
            tags = f" [{tags_str}]" if tags_str else ""
            date = mem.created_at.strftime("%Y-%m-%d %H:%M")
            lines.append(f"[{mem.id}] ({date}){tags} {mem.content}")
        return "\n".join(lines)

    return cast("Callable[..., Coroutine[Any, Any, str]]", search_memory)


def make_save_memory_tool(
    memory_store: MemoryStore,
) -> Callable[..., Coroutine[Any, Any, str]]:
    """Create a save_memory tool bound to a MemoryStore instance."""

    @tool(
        name="save_memory",
        public_description="Save a note to memory. Params: content (str), tags (str or list, default '').",

        tags=["memory", "builtin"],
        capabilities=[MEMORY_WRITE],
    )
    async def save_memory(content: str, tags: str | list[str] = "") -> str:
        """Save a note to long-term memory.

        Args:
            content: The text content to remember
            tags: Comma-separated tags or list of tags for categorization
                  (e.g., "project, todo" or ["project", "todo"])

        Returns:
            Confirmation with the memory ID.
        """
        if isinstance(tags, list):
            tag_list = tags
        elif tags:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        else:
            tag_list = []
        # Associate with current session and user identity (set by orchestrator)
        session_id = current_session_id.get()
        platform = current_platform.get()
        platform_user = current_platform_user.get()
        mem = await memory_store.save(
            content=content, tags=tag_list, session_id=session_id,
            platform=platform, platform_user=platform_user,
        )
        preview = content[:80] + ("..." if len(content) > 80 else "")
        return f"Saved memory {mem.id}: {preview}"

    return cast("Callable[..., Coroutine[Any, Any, str]]", save_memory)


def make_list_memories_tool(
    memory_store: MemoryStore,
) -> Callable[..., Coroutine[Any, Any, str]]:
    """Create a list_memories tool bound to a MemoryStore instance."""

    @tool(
        name="list_memories",
        public_description="List recent memories. Params: tag (str, default ''), limit (int, default 20).",

        tags=["memory", "builtin"],
        capabilities=[MEMORY_READ],
    )
    async def list_memories(tag: str = "", limit: int = 20) -> str:
        """List recent memories from long-term storage.

        Args:
            tag: Optional tag to filter by (e.g., "project")
            limit: Maximum number of results (default 20)

        Returns:
            Formatted list of memories.
        """
        tag_filter = tag if tag else None
        # Scope to current user identity (set by orchestrator in process_turn)
        results = await memory_store.list_memories(tag=tag_filter, limit=limit)
        if not results:
            suffix = f" (filtered by tag: {tag})" if tag else ""
            return f"No memories found.{suffix}"

        lines = []
        for mem in results:
            tags_str = ", ".join(mem.tags) if mem.tags else ""
            tags = f" [{tags_str}]" if tags_str else ""
            date = mem.created_at.strftime("%Y-%m-%d %H:%M")
            lines.append(f"[{mem.id}] ({date}){tags} {mem.content}")
        return "\n".join(lines)

    return cast("Callable[..., Coroutine[Any, Any, str]]", list_memories)


def make_delete_memory_tool(store: MemoryStore) -> Callable[..., Coroutine[Any, Any, str]]:
    """Tool: delete a memory record by id. Requires confirmation by default."""

    @tool(
        name="delete_memory",
        public_description="Delete a memory by id. Params: memory_id (str).",

        tags=["memory", "builtin"],
        capabilities=[MEMORY_WRITE],
        requires_confirmation=True,
    )
    async def delete_memory(memory_id: str) -> str:
        deleted = await store.delete(memory_id)
        if not deleted:
            return f"No memory with id {memory_id}"
        return f"Deleted memory {memory_id}"

    return cast("Callable[..., Coroutine[Any, Any, str]]", delete_memory)
