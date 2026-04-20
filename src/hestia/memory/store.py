"""Long-term memory store using SQLite FTS5 full-text search."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa

from hestia.core.clock import utcnow
from hestia.persistence.db import Database


@dataclass
class Memory:
    """A single memory entry."""

    id: str
    content: str
    tags: str  # space-separated tags
    created_at: datetime
    session_id: str | None  # which session created this memory
    platform: str | None = None  # platform identifier (e.g. "cli", "matrix")
    platform_user: str | None = None  # user identifier on that platform


class MemoryStore:
    """FTS5-backed memory store for searchable long-term notes.

    Uses a SQLite FTS5 virtual table for full-text search when available,
    falling back to a regular table with LIKE queries on SQLite builds
    without FTS5. The table is created via raw DDL because SQLAlchemy
    doesn't support virtual tables through its Table/MetaData API.

    Datetimes: All timestamps are UTC (utcnow()), consistent
    with SessionStore and SchedulerStore. No timezone handling.
    """

    def __init__(self, db: Database) -> None:
        self._db = db
        self._fts5_available = True

    async def create_table(self) -> None:
        """Create the memory table, migrating from old schema if needed.

        Call this during startup alongside db.create_tables().
        """
        async with self._db.engine.connect() as conn:
            # Clean up any leftover probe table from a prior failed run
            await conn.execute(sa.text("DROP TABLE IF EXISTS _fts5_probe"))

            # Detect FTS5 support
            try:
                await conn.execute(
                    sa.text("CREATE VIRTUAL TABLE _fts5_probe USING fts5(x)")
                )
                await conn.execute(sa.text("DROP TABLE _fts5_probe"))
                self._fts5_available = True
            except Exception:
                self._fts5_available = False

            # Check if an old-schema table exists (no platform/platform_user)
            old_schema_exists = False
            try:
                await conn.execute(sa.text("SELECT 1 FROM memory LIMIT 1"))
                try:
                    await conn.execute(sa.text("SELECT platform FROM memory LIMIT 1"))
                except Exception:
                    old_schema_exists = True
            except Exception:
                pass  # Table does not exist at all (fresh database)

            if old_schema_exists and self._fts5_available:
                await conn.execute(sa.text("DROP TABLE IF EXISTS _memory_backup"))
                await conn.execute(
                    sa.text(
                        "CREATE TABLE _memory_backup AS "
                        "SELECT id, content, tags, session_id, created_at FROM memory"
                    )
                )
                await conn.execute(sa.text("DROP TABLE memory"))
                await self._create_fts5_table(conn)
                await conn.execute(
                    sa.text(
                        "INSERT INTO memory(id, content, tags, session_id, "
                        "created_at, platform, platform_user) "
                        "SELECT id, content, tags, session_id, "
                        "created_at, NULL, NULL FROM _memory_backup"
                    )
                )
                await conn.execute(sa.text("DROP TABLE _memory_backup"))
            elif self._fts5_available:
                await self._create_fts5_table(conn)
            else:
                await self._create_regular_table(conn)

            await conn.commit()

    async def _create_fts5_table(self, conn: Any) -> None:
        ddl = """
        CREATE VIRTUAL TABLE IF NOT EXISTS memory USING fts5(
            id UNINDEXED,
            content,
            tags,
            session_id UNINDEXED,
            created_at UNINDEXED,
            platform UNINDEXED,
            platform_user UNINDEXED
        )
        """
        await conn.execute(sa.text(ddl))

    async def _create_regular_table(self, conn: Any) -> None:
        ddl = """
        CREATE TABLE IF NOT EXISTS memory (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            tags TEXT,
            session_id TEXT,
            created_at TEXT,
            platform TEXT,
            platform_user TEXT
        )
        """
        await conn.execute(sa.text(ddl))
        await conn.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS idx_memory_user "
                "ON memory (platform, platform_user)"
            )
        )
        await conn.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS idx_memory_created "
                "ON memory (created_at DESC)"
            )
        )

    def _get_user_scope(self) -> tuple[str | None, str | None]:
        """Read current user identity from runtime ContextVars."""
        from hestia.runtime_context import current_platform, current_platform_user

        platform = current_platform.get()
        platform_user = current_platform_user.get()
        return platform, platform_user

    async def save(
        self,
        content: str,
        tags: list[str] | None = None,
        session_id: str | None = None,
        platform: str | None = None,
        platform_user: str | None = None,
    ) -> Memory:
        """Save a memory entry.

        Args:
            content: The text content to remember
            tags: Optional list of tags for categorization
            session_id: Optional session ID that created this memory
            platform: Optional platform identifier; falls back to runtime ContextVar
            platform_user: Optional user identifier; falls back to runtime ContextVar

        Returns:
            The created Memory
        """
        if platform is None or platform_user is None:
            ctx_platform, ctx_platform_user = self._get_user_scope()
            if platform is None:
                platform = ctx_platform
            if platform_user is None:
                platform_user = ctx_platform_user

        memory_id = f"mem_{uuid.uuid4().hex[:16]}"
        tag_str = " ".join(tags) if tags else ""
        now = utcnow()

        insert = sa.text(
            "INSERT INTO memory (id, content, tags, session_id, created_at, "
            "platform, platform_user) "
            "VALUES (:id, :content, :tags, :session_id, :created_at, "
            ":platform, :platform_user)"
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
                    "platform": platform,
                    "platform_user": platform_user,
                },
            )
            await conn.commit()

        return Memory(
            id=memory_id,
            content=content,
            tags=tag_str,
            session_id=session_id,
            created_at=now,
            platform=platform,
            platform_user=platform_user,
        )

    async def search(
        self,
        query: str,
        limit: int = 5,
        platform: str | None = None,
        platform_user: str | None = None,
    ) -> list[Memory]:
        """Search memories using FTS5 full-text search or LIKE fallback.

        Args:
            query: Search query (FTS5 syntax when available: AND, OR, NOT, "phrases")
            limit: Maximum number of results
            platform: Optional platform filter; falls back to runtime ContextVar
            platform_user: Optional user filter; falls back to runtime ContextVar

        Returns:
            List of matching memories, ordered by relevance (BM25 rank) or recency
        """
        if platform is None or platform_user is None:
            ctx_platform, ctx_platform_user = self._get_user_scope()
            if platform is None:
                platform = ctx_platform
            if platform_user is None:
                platform_user = ctx_platform_user

        params: dict[str, Any] = {"limit": limit}

        if self._fts5_available:
            params["query"] = query
            if platform is not None and platform_user is not None:
                sql = sa.text(
                    "SELECT id, content, tags, session_id, created_at, platform, platform_user "
                    "FROM memory WHERE memory MATCH :query "
                    "AND platform = :platform AND platform_user = :platform_user "
                    "ORDER BY rank LIMIT :limit"
                )
                params["platform"] = platform
                params["platform_user"] = platform_user
            else:
                sql = sa.text(
                    "SELECT id, content, tags, session_id, created_at, platform, platform_user "
                    "FROM memory WHERE memory MATCH :query "
                    "ORDER BY rank LIMIT :limit"
                )
        else:
            # LIKE fallback for SQLite builds without FTS5
            params["query"] = f"%{query}%"
            if platform is not None and platform_user is not None:
                sql = sa.text(
                    "SELECT id, content, tags, session_id, created_at, platform, platform_user "
                    "FROM memory WHERE content LIKE :query "
                    "AND platform = :platform AND platform_user = :platform_user "
                    "ORDER BY created_at DESC LIMIT :limit"
                )
                params["platform"] = platform
                params["platform_user"] = platform_user
            else:
                sql = sa.text(
                    "SELECT id, content, tags, session_id, created_at, platform, platform_user "
                    "FROM memory WHERE content LIKE :query "
                    "ORDER BY created_at DESC LIMIT :limit"
                )

        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, params)
            rows = result.fetchall()
            return [self._row_to_memory(row) for row in rows]

    async def list_memories(
        self,
        tag: str | None = None,
        limit: int = 20,
        platform: str | None = None,
        platform_user: str | None = None,
    ) -> list[Memory]:
        """List memories, optionally filtered by tag and user scope.

        Args:
            tag: Optional tag to filter by
            limit: Maximum number of results
            platform: Optional platform filter; falls back to runtime ContextVar
            platform_user: Optional user filter; falls back to runtime ContextVar

        Returns:
            List of memories, newest first
        """
        if platform is None or platform_user is None:
            ctx_platform, ctx_platform_user = self._get_user_scope()
            if platform is None:
                platform = ctx_platform
            if platform_user is None:
                platform_user = ctx_platform_user

        params: dict[str, Any] = {"limit": limit}
        where_clauses: list[str] = []

        if tag:
            if self._fts5_available:
                quoted_tag = f'"{tag}"'
                where_clauses.append("tags MATCH :tag")
                params["tag"] = quoted_tag
            else:
                where_clauses.append(
                    "(tags = :tag OR tags LIKE :p0 OR tags LIKE :p1 OR tags LIKE :p2)"
                )
                params["tag"] = tag
                params["p0"] = f"{tag} %"
                params["p1"] = f"% {tag} %"
                params["p2"] = f"% {tag}"

        if platform is not None and platform_user is not None:
            where_clauses.append("platform = :platform AND platform_user = :platform_user")
            params["platform"] = platform
            params["platform_user"] = platform_user

        where_str = ""
        if where_clauses:
            where_str = "WHERE " + " AND ".join(where_clauses)

        sql = sa.text(
            f"SELECT id, content, tags, session_id, created_at, platform, platform_user "
            f"FROM memory {where_str} "
            f"ORDER BY created_at DESC LIMIT :limit"
        )

        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, params)
            rows = result.fetchall()
            return [self._row_to_memory(row) for row in rows]

    async def delete(
        self,
        memory_id: str,
        platform: str | None = None,
        platform_user: str | None = None,
    ) -> bool:
        """Delete a memory by ID.

        When platform and platform_user are provided (or available via
        runtime ContextVars), the deletion is scoped to that user.

        Returns True if the memory was found and deleted.
        """
        if platform is None or platform_user is None:
            ctx_platform, ctx_platform_user = self._get_user_scope()
            if platform is None:
                platform = ctx_platform
            if platform_user is None:
                platform_user = ctx_platform_user

        if platform is not None and platform_user is not None:
            sql = sa.text(
                "DELETE FROM memory WHERE id = :id "
                "AND platform = :platform AND platform_user = :platform_user"
            )
            params = {"id": memory_id, "platform": platform, "platform_user": platform_user}
        else:
            sql = sa.text("DELETE FROM memory WHERE id = :id")
            params = {"id": memory_id}

        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, params)
            await conn.commit()
            return result.rowcount > 0

    async def count(
        self,
        platform: str | None = None,
        platform_user: str | None = None,
    ) -> int:
        """Return the total number of memories, optionally scoped to a user."""
        if platform is None or platform_user is None:
            ctx_platform, ctx_platform_user = self._get_user_scope()
            if platform is None:
                platform = ctx_platform
            if platform_user is None:
                platform_user = ctx_platform_user

        if platform is not None and platform_user is not None:
            sql = sa.text(
                "SELECT COUNT(*) FROM memory "
                "WHERE platform = :platform AND platform_user = :platform_user"
            )
            params = {"platform": platform, "platform_user": platform_user}
        else:
            sql = sa.text("SELECT COUNT(*) FROM memory")
            params = {}

        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, params)
            return result.scalar() or 0

    def _row_to_memory(self, row: Any) -> Memory:
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
            platform=row.platform if hasattr(row, "platform") else None,
            platform_user=row.platform_user if hasattr(row, "platform_user") else None,
        )
