"""Long-term memory store using SQLite FTS5 full-text search."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa

from hestia.persistence.db import Database


@dataclass
class Memory:
    """A single memory entry."""

    id: str
    content: str
    tags: str  # space-separated tags
    created_at: datetime
    session_id: str | None  # which session created this memory


class MemoryStore:
    """FTS5-backed memory store for searchable long-term notes.

    Uses a SQLite FTS5 virtual table for full-text search. The table
    is created via raw DDL because SQLAlchemy doesn't support virtual
    tables through its Table/MetaData API.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create_table(self) -> None:
        """Create the FTS5 virtual table if it doesn't exist.

        Call this during startup alongside db.create_tables().
        """
        ddl = """
        CREATE VIRTUAL TABLE IF NOT EXISTS memory USING fts5(
            id UNINDEXED,
            content,
            tags,
            session_id UNINDEXED,
            created_at UNINDEXED
        )
        """
        async with self._db.engine.connect() as conn:
            await conn.execute(sa.text(ddl))
            await conn.commit()

    async def save(
        self,
        content: str,
        tags: list[str] | None = None,
        session_id: str | None = None,
    ) -> Memory:
        """Save a memory entry.

        Args:
            content: The text content to remember
            tags: Optional list of tags for categorization
            session_id: Optional session ID that created this memory

        Returns:
            The created Memory
        """
        memory_id = f"mem_{uuid.uuid4().hex[:16]}"
        tag_str = " ".join(tags) if tags else ""
        now = datetime.now()

        insert = sa.text(
            "INSERT INTO memory (id, content, tags, session_id, created_at) "
            "VALUES (:id, :content, :tags, :session_id, :created_at)"
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(
                insert,
                {
                    "id": memory_id,
                    "content": content,
                    "tags": tag_str,
                    "session_id": session_id,
                    "created_at": now.isoformat(),
                },
            )
            await conn.commit()

        return Memory(
            id=memory_id,
            content=content,
            tags=tag_str,
            session_id=session_id,
            created_at=now,
        )

    async def search(
        self,
        query: str,
        limit: int = 5,
    ) -> list[Memory]:
        """Search memories using FTS5 full-text search.

        Args:
            query: Search query (supports FTS5 syntax: AND, OR, NOT, "phrases")
            limit: Maximum number of results

        Returns:
            List of matching memories, ordered by relevance (BM25 rank)
        """
        # FTS5 MATCH with BM25 ranking
        sql = sa.text(
            "SELECT id, content, tags, session_id, created_at "
            "FROM memory WHERE memory MATCH :query "
            "ORDER BY rank "
            "LIMIT :limit"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"query": query, "limit": limit})
            rows = result.fetchall()
            return [self._row_to_memory(row) for row in rows]

    async def list_memories(
        self,
        tag: str | None = None,
        limit: int = 20,
    ) -> list[Memory]:
        """List memories, optionally filtered by tag.

        Args:
            tag: Optional tag to filter by
            limit: Maximum number of results

        Returns:
            List of memories, newest first
        """
        if tag:
            # FTS5 can search within the tags column
            sql = sa.text(
                "SELECT id, content, tags, session_id, created_at "
                "FROM memory WHERE tags MATCH :tag "
                "ORDER BY created_at DESC "
                "LIMIT :limit"
            )
            params = {"tag": tag, "limit": limit}
        else:
            sql = sa.text(
                "SELECT id, content, tags, session_id, created_at "
                "FROM memory "
                "ORDER BY created_at DESC "
                "LIMIT :limit"
            )
            params = {"limit": limit}

        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, params)
            rows = result.fetchall()
            return [self._row_to_memory(row) for row in rows]

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID.

        Returns True if the memory was found and deleted.
        """
        sql = sa.text("DELETE FROM memory WHERE id = :id")
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"id": memory_id})
            await conn.commit()
            return result.rowcount > 0

    async def count(self) -> int:
        """Return the total number of memories."""
        sql = sa.text("SELECT COUNT(*) FROM memory")
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql)
            return result.scalar() or 0

    def _row_to_memory(self, row) -> Memory:
        """Convert a database row to a Memory dataclass."""
        created_at = row.created_at
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        return Memory(
            id=row.id,
            content=row.content,
            tags=row.tags,
            session_id=row.session_id,
            created_at=created_at,
        )
