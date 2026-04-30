"""Long-term memory store using SQLite FTS5 full-text search."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.exc import DatabaseError, OperationalError

from hestia.core.clock import utcnow
from hestia.errors import PersistenceError
from hestia.persistence.db import Database

logger = logging.getLogger(__name__)


def _sanitize_fts5_query(query: str) -> str:
    """Escape a raw query so FTS5 does not misinterpret special characters.

    FTS5 treats hyphens, colons, asterisks, carets, and other punctuation
    as operators or column specifiers. Wrapping the query in double quotes
    forces FTS5 to treat it as a literal phrase, which is what users expect
    for simple keyword/tag searches.

    If the query already contains explicit FTS5 operators (AND, OR, NOT)
    or is already quoted, it is returned unchanged so advanced syntax
    continues to work.
    """
    stripped = query.strip()
    if stripped.startswith('"') and stripped.endswith('"'):
        return query
    if any(op in stripped.upper() for op in (" AND ", " OR ", " NOT ")):
        return query
    # Hyphens, colons, asterisks, and carets are the most common characters
    # that trigger "no such column" or syntax errors in FTS5.
    if "-" in stripped or ":" in stripped or "*" in stripped or "^" in stripped:
        escaped = stripped.replace('"', '""')
        return f'"{escaped}"'
    return query


@dataclass
class Memory:
    """A single memory entry."""

    id: str
    content: str
    tags: list[str]  # pipe-delimited in DB, list in Python
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
        self._fts5_probed = False

    async def _probe_fts5(self, conn: Any) -> None:
        """Detect FTS5 support once per instance."""
        if self._fts5_probed:
            return
        await conn.execute(sa.text("DROP TABLE IF EXISTS _fts5_probe"))
        try:
            await conn.execute(
                sa.text("CREATE VIRTUAL TABLE _fts5_probe USING fts5(x)")
            )
            await conn.execute(sa.text("DROP TABLE _fts5_probe"))
            self._fts5_available = True
        except (OperationalError, DatabaseError) as exc:
            logger.info(
                "FTS5 unavailable (%s: %s); falling back to LIKE queries",
                type(exc).__name__,
                exc,
            )
            self._fts5_available = False
        except Exception:  # noqa: BLE001
            # FTS5 probe failure should not block startup.
            logger.exception(
                "Unexpected error while probing SQLite FTS5 support — "
                "treating as unavailable so startup can proceed, but this "
                "should be investigated"
            )
            self._fts5_available = False
        finally:
            self._fts5_probed = True

    async def create_table(self) -> None:
        """Create the memory table, migrating from old schema if needed.

        Call this during startup alongside db.create_tables().

        Note: This method is NOT managed by alembic because SQLite FTS5
        virtual tables are not supported by SQLAlchemy's Table/MetaData
        API. Alembic can only manage regular tables, so FTS5 DDL is
        handled here via raw SQL.
        """
        async with self._db.engine.connect() as conn:
            await self._probe_fts5(conn)

            # Check if an old-schema table exists (no platform/platform_user)
            old_schema_exists = False
            try:
                await conn.execute(sa.text("SELECT 1 FROM memory LIMIT 1"))
                try:
                    await conn.execute(sa.text("SELECT platform FROM memory LIMIT 1"))
                except sa.exc.OperationalError:
                    old_schema_exists = True
            except sa.exc.OperationalError:
                logger.debug("memory table does not exist (fresh database)", exc_info=True)

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

            # Runtime schema version check: verify expected columns exist
            try:
                await conn.execute(
                    sa.text("SELECT platform, platform_user FROM memory LIMIT 1")
                )
            except OperationalError as exc:
                raise PersistenceError(
                    "Memory table schema mismatch: expected columns "
                    "'platform' and 'platform_user'. Run 'hestia init' to recreate."
                ) from exc

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

    def _resolve_scope(
        self, platform: str | None, platform_user: str | None
    ) -> tuple[str | None, str | None]:
        """Fill in missing platform/user from runtime ContextVars."""
        if platform is None or platform_user is None:
            ctx_platform, ctx_platform_user = self._get_user_scope()
            if platform is None:
                platform = ctx_platform
            if platform_user is None:
                platform_user = ctx_platform_user
        if (platform is None) != (platform_user is None):
            logger.warning(
                "Partial identity context (platform=%r, platform_user=%r); "
                "treating as unscoped to avoid isolation leak",
                platform,
                platform_user,
            )
            platform = None
            platform_user = None
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
        platform, platform_user = self._resolve_scope(platform, platform_user)
        if platform is None or platform_user is None:
            logger.warning(
                "memory.save called outside an identity context; "
                "saving as unscoped (platform=%r, platform_user=%r)",
                platform,
                platform_user,
            )

        memory_id = f"mem_{uuid.uuid4().hex[:16]}"
        tag_str = "|".join(tags) if tags else ""
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
            tags=tags if tags else [],
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
        platform, platform_user = self._resolve_scope(platform, platform_user)

        params: dict[str, Any] = {"limit": limit}

        if self._fts5_available:
            params["query"] = _sanitize_fts5_query(query)
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
        platform, platform_user = self._resolve_scope(platform, platform_user)

        # Every entry appended to ``where_clauses`` below is a *literal* string fragment
        # chosen by this function's own control flow — never derived from caller input. All
        # user-supplied values (`tag`, `platform`, `platform_user`) flow through ``params``
        # and are bound by SQLAlchemy via the ``:name`` placeholders. That is what makes
        # the f-string assembly below safe.
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
                # pipe-delimited exact-match patterns
                params["p0"] = f"{tag}|%"
                params["p1"] = f"%|{tag}|%"
                params["p2"] = f"%|{tag}"

        if platform is not None and platform_user is not None:
            where_clauses.append("platform = :platform AND platform_user = :platform_user")
            params["platform"] = platform
            params["platform_user"] = platform_user

        where_str = ""
        if where_clauses:
            where_str = "WHERE " + " AND ".join(where_clauses)

        sql = sa.text(
            "SELECT id, content, tags, session_id, created_at, platform, platform_user "
            f"FROM memory {where_str} "
            "ORDER BY created_at DESC LIMIT :limit"
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
        platform, platform_user = self._resolve_scope(platform, platform_user)

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
        platform, platform_user = self._resolve_scope(platform, platform_user)

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
        raw_tags = row.tags or ""
        if "|" in raw_tags:
            tags = raw_tags.split("|")
        elif raw_tags:
            tags = raw_tags.split()
        else:
            tags = []
        return Memory(
            id=row.id,
            content=row.content,
            tags=tags,
            session_id=row.session_id,
            created_at=created_at,
            platform=row.platform,
            platform_user=row.platform_user,
        )
