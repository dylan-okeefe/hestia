"""Memory tools — search and save to long-term memory."""

import contextvars
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, cast

from hestia.memory.store import MemoryStore
from hestia.tools.capabilities import MEMORY_READ, MEMORY_WRITE
from hestia.tools.metadata import tool

if TYPE_CHECKING:
    from hestia.persistence.trace_store import TraceStore

# Context variable to hold the current session ID during tool execution.
# This is set by the orchestrator at the start of process_turn and cleared
# in a finally block. Tools can read this to associate saves with sessions.
current_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_session_id", default=None
)

# Context variable to hold the current TraceStore during tool execution.
# Set by the orchestrator when a turn starts so that network tools can
# record egress events.
current_trace_store: contextvars.ContextVar["TraceStore | None"] = contextvars.ContextVar(
    "current_trace_store", default=None
)


def make_search_memory_tool(
    memory_store: MemoryStore,
) -> Callable[..., Coroutine[Any, Any, str]]:
    """Create a search_memory tool bound to a MemoryStore instance."""

    @tool(
        name="search_memory",
        public_description="Search your long-term memory for previously saved notes.",
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
        results = await memory_store.search(query, limit=limit)
        if not results:
            return "No memories found matching your query."

        lines = []
        for mem in results:
            tags = f" [{mem.tags}]" if mem.tags else ""
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
        public_description="Save a note to long-term memory for future recall.",
        tags=["memory", "builtin"],
        capabilities=[MEMORY_WRITE],
    )
    async def save_memory(content: str, tags: str = "") -> str:
        """Save a note to long-term memory.

        Args:
            content: The text content to remember
            tags: Space-separated tags for categorization (e.g., "project todo")

        Returns:
            Confirmation with the memory ID.
        """
        tag_list = tags.split() if tags else []
        # Associate with current session if running inside orchestrator
        session_id = current_session_id.get()
        mem = await memory_store.save(content=content, tags=tag_list, session_id=session_id)
        preview = content[:80] + ("..." if len(content) > 80 else "")
        return f"Saved memory {mem.id}: {preview}"

    return cast("Callable[..., Coroutine[Any, Any, str]]", save_memory)


def make_list_memories_tool(
    memory_store: MemoryStore,
) -> Callable[..., Coroutine[Any, Any, str]]:
    """Create a list_memories tool bound to a MemoryStore instance."""

    @tool(
        name="list_memories",
        public_description="List recent memories, optionally filtered by tag.",
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
        results = await memory_store.list_memories(tag=tag_filter, limit=limit)
        if not results:
            suffix = f" (filtered by tag: {tag})" if tag else ""
            return f"No memories found.{suffix}"

        lines = []
        for mem in results:
            tags = f" [{mem.tags}]" if mem.tags else ""
            date = mem.created_at.strftime("%Y-%m-%d %H:%M")
            lines.append(f"[{mem.id}] ({date}){tags} {mem.content}")
        return "\n".join(lines)

    return cast("Callable[..., Coroutine[Any, Any, str]]", list_memories)


def make_delete_memory_tool(store: MemoryStore) -> Callable[..., Coroutine[Any, Any, str]]:
    """Tool: delete a memory record by id. Requires confirmation by default."""

    @tool(
        name="delete_memory",
        public_description="Delete a memory record by its id. Use list_memories to find ids.",
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
