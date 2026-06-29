"""Long-term memory store using SQLite FTS5 full-text search."""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.exc import DatabaseError, OperationalError

from hestia.config import MemoryConfig
from hestia.core.clock import utcnow
from hestia.errors import PersistenceError
from hestia.memory.sanitizer import MemorySanitizer
from hestia.persistence.db import Database

logger = logging.getLogger(__name__)


def _sanitize_fts5_query(query: str) -> str:
    """Escape a raw query so FTS5 does not misinterpret special characters.

    FTS5 treats hyphens, colons, periods, asterisks, carets, and other
    punctuation as operators or column specifiers. Wrapping the query in
    double quotes forces FTS5 to treat it as a literal phrase, which is what
    users expect for simple keyword/tag searches.

    If the query already contains explicit FTS5 operators (AND, OR, NOT)
    or is already quoted, it is returned unchanged so advanced syntax
    continues to work.
    """
    stripped = query.strip()
    if stripped.startswith('"') and stripped.endswith('"'):
        return query
    if any(op in stripped.upper() for op in (" AND ", " OR ", " NOT ")):
        return query
    # Any non-word, non-whitespace character can trigger an FTS5 syntax error
    # (e.g., "fts5: syntax error near '.'"). Quote the whole phrase so these
    # characters are treated literally.
    if re.search(r"[^\w\s]", stripped):
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
    is_active: bool = True
    deleted_at: datetime | None = None
    deleted_reason: str | None = None
    superseded_by: str | None = None
    is_pinned: bool = False
    is_user_authored: bool = False
    last_recalled_at: datetime | None = None
    is_global: bool = False  # always-inject scope; migrated existing memories are True


class MemoryStore:
    """FTS5-backed memory store for searchable long-term notes.

    Uses a SQLite FTS5 virtual table for full-text search when available,
    falling back to a regular table with LIKE queries on SQLite builds
    without FTS5. The table is created via raw DDL because SQLAlchemy
    doesn't support virtual tables through its Table/MetaData API.

    Datetimes: All timestamps are UTC (utcnow()), consistent
    with SessionStore and SchedulerStore. No timezone handling.
    """

    def __init__(self, db: Database, config: MemoryConfig | None = None) -> None:
        self._db = db
        self._config = config or MemoryConfig()
        self._fts5_available = True
        self._fts5_probed = False
        self._sanitizer = MemorySanitizer()

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

            table_exists = await self._memory_table_exists(conn)
            needs_recreate = False
            if table_exists:
                missing = await self._missing_memory_columns(conn)
                if missing:
                    if self._fts5_available:
                        needs_recreate = True
                    else:
                        # Regular table: use ALTER TABLE for missing columns.
                        for col in missing:
                            await self._add_memory_column(conn, col)

            if needs_recreate:
                await self._recreate_memory_table_with_backup(conn)
            elif not table_exists:
                if self._fts5_available:
                    await self._create_fts5_table(conn)
                else:
                    await self._create_regular_table(conn)

            # Runtime schema version check: verify expected columns exist
            try:
                await conn.execute(
                    sa.text(
                        "SELECT platform, platform_user, is_active, deleted_at, "
                        "deleted_reason, superseded_by, is_pinned, is_user_authored, "
                        "last_recalled_at, is_global FROM memory LIMIT 1"
                    )
                )
            except OperationalError as exc:
                raise PersistenceError(
                    "Memory table schema mismatch: expected columns "
                    "'platform', 'platform_user', is_active, deleted_at, "
                    "deleted_reason, superseded_by, is_pinned, is_user_authored, "
                    "last_recalled_at, is_global. Run 'hestia init' to recreate."
                ) from exc

            # Migrate any pre-topic-scoped memories to global on first startup.
            await self._migrate_existing_to_global(conn)

            await conn.commit()

    @staticmethod
    async def _memory_table_exists(conn: Any) -> bool:
        try:
            await conn.execute(sa.text("SELECT 1 FROM memory LIMIT 1"))
            return True
        except sa.exc.OperationalError:
            return False

    _EXPECTED_MEMORY_COLUMNS = [
        "id",
        "content",
        "tags",
        "session_id",
        "created_at",
        "platform",
        "platform_user",
        "is_active",
        "deleted_at",
        "deleted_reason",
        "superseded_by",
        "is_pinned",
        "is_user_authored",
        "last_recalled_at",
        "is_global",
    ]

    async def _missing_memory_columns(self, conn: Any) -> list[str]:
        """Return expected columns that are not present in the existing table."""
        present: set[str] = set()
        for col in self._EXPECTED_MEMORY_COLUMNS:
            try:
                await conn.execute(sa.text(f"SELECT {col} FROM memory LIMIT 1"))
                present.add(col)
            except sa.exc.OperationalError:
                pass
        return [col for col in self._EXPECTED_MEMORY_COLUMNS if col not in present]

    async def _migrate_existing_to_global(self, conn: Any) -> None:
        """Set is_global=1 for any legacy rows where the flag is NULL.

        Idempotent: rows already marked global or non-global are untouched.
        This implements the Loop A rollout rule that all pre-existing memories
        become global so nothing is dropped or re-scoped automatically.
        """
        await conn.execute(
            sa.text(
                "UPDATE memory SET is_global = 1 "
                "WHERE is_global IS NULL"
            )
        )

    async def _add_memory_column(self, conn: Any, column: str) -> None:
        """Add a single column to a regular (non-FTS5) memory table."""
        defaults: dict[str, str] = {
            "is_active": "INTEGER NOT NULL DEFAULT 1",
            "is_pinned": "INTEGER NOT NULL DEFAULT 0",
            "is_user_authored": "INTEGER NOT NULL DEFAULT 0",
            # Legacy memories must become global on migration (decision #10).
            "is_global": "INTEGER NOT NULL DEFAULT 1",
            "deleted_at": "TEXT",
            "deleted_reason": "TEXT",
            "superseded_by": "TEXT",
            "last_recalled_at": "TEXT",
            "platform": "TEXT",
            "platform_user": "TEXT",
        }
        ddl = defaults.get(column)
        if ddl is None:
            raise PersistenceError(f"Unknown memory column to add: {column}")
        await conn.execute(sa.text(f"ALTER TABLE memory ADD COLUMN {column} {ddl}"))

    async def _recreate_memory_table_with_backup(self, conn: Any) -> None:
        """Backup all existing columns, recreate FTS5 table, restore data.

        Handles migration from any prior schema variant by introspecting which
        columns are present before backing up.
        """
        existing = [
            col
            for col in self._EXPECTED_MEMORY_COLUMNS
            if col in await self._present_memory_columns(conn)
        ]
        # id/content/tags/session_id/created_at have always existed.
        select_cols = ", ".join(existing)
        await conn.execute(sa.text("DROP TABLE IF EXISTS _memory_backup"))
        await conn.execute(
            sa.text(f"CREATE TABLE _memory_backup AS SELECT {select_cols} FROM memory")
        )
        await conn.execute(sa.text("DROP TABLE memory"))
        await self._create_fts5_table(conn)

        # Build INSERT that provides defaults for any missing columns.
        all_cols = ", ".join(self._EXPECTED_MEMORY_COLUMNS)
        source_cols = []
        for col in self._EXPECTED_MEMORY_COLUMNS:
            if col in existing:
                source_cols.append(col)
            elif col == "is_active":
                source_cols.append("1")
            elif col in ("is_pinned", "is_user_authored"):
                source_cols.append("0")
            elif col == "is_global":
                # Pre-topic-scoped memories become global on migration.
                source_cols.append("1")
            else:
                source_cols.append("NULL")
        values = ", ".join(source_cols)
        await conn.execute(
            sa.text(f"INSERT INTO memory({all_cols}) SELECT {values} FROM _memory_backup")
        )
        await conn.execute(sa.text("DROP TABLE _memory_backup"))

    async def _present_memory_columns(self, conn: Any) -> set[str]:
        """Return the set of columns that exist in the current memory table."""
        present: set[str] = set()
        for col in self._EXPECTED_MEMORY_COLUMNS:
            try:
                await conn.execute(sa.text(f"SELECT {col} FROM memory LIMIT 1"))
                present.add(col)
            except sa.exc.OperationalError:
                pass
        return present

    async def _create_fts5_table(self, conn: Any) -> None:
        ddl = """
        CREATE VIRTUAL TABLE IF NOT EXISTS memory USING fts5(
            id UNINDEXED,
            content,
            tags,
            session_id UNINDEXED,
            created_at UNINDEXED,
            platform UNINDEXED,
            platform_user UNINDEXED,
            is_active UNINDEXED,
            deleted_at UNINDEXED,
            deleted_reason UNINDEXED,
            superseded_by UNINDEXED,
            is_pinned UNINDEXED,
            is_user_authored UNINDEXED,
            last_recalled_at UNINDEXED,
            is_global UNINDEXED
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
            platform_user TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            deleted_at TEXT,
            deleted_reason TEXT,
            superseded_by TEXT,
            is_pinned INTEGER NOT NULL DEFAULT 0,
            is_user_authored INTEGER NOT NULL DEFAULT 0,
            last_recalled_at TEXT,
            is_global INTEGER NOT NULL DEFAULT 0
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
        strict: bool = False,
        is_global: bool = False,
        topic_ids: list[str] | None = None,
    ) -> Memory | None:
        """Save a memory entry.

        Args:
            content: The text content to remember
            tags: Optional list of tags for categorization
            session_id: Optional session ID that created this memory
            platform: Optional platform identifier; falls back to runtime ContextVar
            platform_user: Optional user identifier; falls back to runtime ContextVar
            strict: If True, raise PersistenceError when content is rejected.
            is_global: When True, the memory is always injected regardless of topic.
            topic_ids: Topic IDs to associate with this memory. Ignored when
                is_global is True.

        Returns:
            The created Memory, or None when the content is rejected by the sanitizer.
        """
        result = self._sanitizer.sanitize(content)
        if result.rejected:
            logger.warning(
                "Memory content rejected by sanitizer: %s",
                result.reason,
            )
            if strict:
                raise PersistenceError(
                    f"Memory content rejected by sanitizer: {result.reason}"
                )
            return None

        # Use the cleaned content from the sanitizer (e.g., stripped whitespace).
        clean_content = result.content or content

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
            "platform, platform_user, is_active, deleted_at, deleted_reason, "
            "superseded_by, is_pinned, is_user_authored, last_recalled_at, is_global) "
            "VALUES (:id, :content, :tags, :session_id, :created_at, "
            ":platform, :platform_user, :is_active, :deleted_at, :deleted_reason, "
            ":superseded_by, :is_pinned, :is_user_authored, :last_recalled_at, :is_global)"
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(
                insert,
                {
                    "id": memory_id,
                    "content": clean_content,
                    "tags": tag_str,
                    "session_id": session_id,
                    "created_at": now.isoformat(),
                    "platform": platform,
                    "platform_user": platform_user,
                    "is_active": 1,
                    "deleted_at": None,
                    "deleted_reason": None,
                    "superseded_by": None,
                    "is_pinned": 0,
                    "is_user_authored": 0,
                    "last_recalled_at": None,
                    "is_global": 1 if is_global else 0,
                },
            )

            if not is_global and topic_ids:
                await self._associate_memory_with_topics(
                    conn, memory_id, topic_ids, now
                )
            elif not is_global and not topic_ids:
                logger.debug(
                    "Saving non-global memory %s without topic associations",
                    memory_id,
                )

            await conn.commit()

        return Memory(
            id=memory_id,
            content=clean_content,
            tags=tags if tags else [],
            session_id=session_id,
            created_at=now,
            platform=platform,
            platform_user=platform_user,
            is_global=is_global,
        )

    async def save_global(
        self,
        content: str,
        tags: list[str] | None = None,
        session_id: str | None = None,
        platform: str | None = None,
        platform_user: str | None = None,
        strict: bool = False,
    ) -> Memory | None:
        """Save a memory as global (always-inject scope).

        Convenience wrapper around :meth:`save` with ``is_global=True``.
        """
        return await self.save(
            content=content,
            tags=tags,
            session_id=session_id,
            platform=platform,
            platform_user=platform_user,
            strict=strict,
            is_global=True,
        )

    async def _associate_memory_with_topics(
        self,
        conn: Any,
        memory_id: str,
        topic_ids: list[str],
        created_at: datetime,
    ) -> None:
        """Insert memory_topics rows associating a memory with topics.

        Duplicate topic IDs are ignored (PRIMARY KEY prevents duplicates).
        """
        if not topic_ids:
            return
        seen = set()
        values = []
        for topic_id in topic_ids:
            if topic_id in seen:
                continue
            seen.add(topic_id)
            values.append(
                {
                    "memory_id": memory_id,
                    "topic_id": topic_id,
                    "created_at": created_at.isoformat(),
                }
            )
        if values:
            await conn.execute(
                sa.text(
                    "INSERT OR IGNORE INTO memory_topics "
                    "(memory_id, topic_id, created_at) "
                    "VALUES (:memory_id, :topic_id, :created_at)"
                ),
                values,
            )

    async def get_for_epoch(
        self,
        *,
        platform: str,
        platform_user: str,
        topic_ids: list[str] | None = None,
        active_sender_platform_user: str | None = None,
        include_inactive: bool = False,
    ) -> tuple[list[Memory], list[Memory]]:
        """Fetch memories for epoch composition.

        Returns two buckets: global memories and topic-scoped memories. Global
        memories use the active sender's identity in group chats; topic memories
        use the room/conversation identity. The caller applies the global cap
        and token budget.

        Args:
            platform: Platform identifier for both scopes.
            platform_user: Conversation/room user identifier for topic memories.
            topic_ids: Subscribed topic IDs. Empty list fetches no topic memories.
            active_sender_platform_user: In group chats, the user whose global
                memories should be included. Defaults to ``platform_user``.
            include_inactive: If True, include soft-deleted memories.

        Returns:
            Tuple of (global_memories, topic_memories), each newest-first.
        """
        global_user = active_sender_platform_user or platform_user
        active_clause = "AND is_active = :is_active" if not include_inactive else ""
        params: dict[str, Any] = {
            "platform": platform,
            "global_user": global_user,
            "room_user": platform_user,
            "is_active": 0 if include_inactive else 1,
        }

        global_sql = sa.text(
            "SELECT id, content, tags, session_id, created_at, platform, platform_user, "
            "is_active, deleted_at, deleted_reason, superseded_by, is_pinned, "
            "is_user_authored, last_recalled_at, is_global "
            "FROM memory "
            "WHERE platform = :platform AND platform_user = :global_user "
            "AND is_global = 1 "
            f"{active_clause} "
            "ORDER BY created_at DESC"
        )

        topic_memories: list[Memory] = []
        if topic_ids:
            placeholders = ", ".join(f":tid_{i}" for i in range(len(topic_ids)))
            for i, topic_id in enumerate(topic_ids):
                params[f"tid_{i}"] = topic_id
            topic_sql = sa.text(
                "SELECT DISTINCT m.id, m.content, m.tags, m.session_id, m.created_at, "
                "m.platform, m.platform_user, m.is_active, m.deleted_at, "
                "m.deleted_reason, m.superseded_by, m.is_pinned, "
                "m.is_user_authored, m.last_recalled_at, m.is_global "
                "FROM memory m "
                "JOIN memory_topics mt ON m.id = mt.memory_id "
                "WHERE m.platform = :platform AND m.platform_user = :room_user "
                f"AND mt.topic_id IN ({placeholders}) "
                "AND m.is_global = 0 "
                f"{active_clause} "
                "ORDER BY m.created_at DESC"
            )
            async with self._db.engine.connect() as conn:
                result = await conn.execute(topic_sql, params)
                topic_memories = [self._row_to_memory(row) for row in result.fetchall()]

        async with self._db.engine.connect() as conn:
            result = await conn.execute(global_sql, params)
            global_memories = [self._row_to_memory(row) for row in result.fetchall()]

        return global_memories, topic_memories

    async def search(
        self,
        query: str,
        limit: int = 5,
        platform: str | None = None,
        platform_user: str | None = None,
        include_inactive: bool = False,
    ) -> list[Memory]:
        """Search memories using FTS5 full-text search or LIKE fallback.

        Args:
            query: Search query (FTS5 syntax when available: AND, OR, NOT, "phrases")
            limit: Maximum number of results
            platform: Optional platform filter; falls back to runtime ContextVar
            platform_user: Optional user filter; falls back to runtime ContextVar
            include_inactive: If True, also return soft-deleted memories.

        Returns:
            List of matching memories, ordered by relevance (BM25 rank) or recency
        """
        platform, platform_user = self._resolve_scope(platform, platform_user)

        params: dict[str, Any] = {"limit": limit, "is_active": 1 if not include_inactive else None}

        if platform is None or platform_user is None:
            # Fail closed: unscoped queries are not allowed
            return []

        active_clause = ""
        if not include_inactive:
            active_clause = "AND is_active = :is_active"

        if self._fts5_available:
            params["query"] = _sanitize_fts5_query(query)
            sql = sa.text(
                "SELECT id, content, tags, session_id, created_at, platform, platform_user, "
                "is_active, deleted_at, deleted_reason, superseded_by, is_pinned, "
                "is_user_authored, last_recalled_at, is_global "
                f"FROM memory WHERE memory MATCH :query {active_clause} "
                "AND platform = :platform AND platform_user = :platform_user "
                "ORDER BY rank LIMIT :limit"
            )
            params["platform"] = platform
            params["platform_user"] = platform_user
        else:
            # LIKE fallback for SQLite builds without FTS5
            params["query"] = f"%{query}%"
            sql = sa.text(
                "SELECT id, content, tags, session_id, created_at, platform, platform_user, "
                "is_active, deleted_at, deleted_reason, superseded_by, is_pinned, "
                "is_user_authored, last_recalled_at, is_global "
                f"FROM memory WHERE content LIKE :query {active_clause} "
                "AND platform = :platform AND platform_user = :platform_user "
                "ORDER BY created_at DESC LIMIT :limit"
            )
            params["platform"] = platform
            params["platform_user"] = platform_user

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
        include_inactive: bool = False,
    ) -> list[Memory]:
        """List memories, optionally filtered by tag and user scope.

        Args:
            tag: Optional tag to filter by
            limit: Maximum number of results
            platform: Optional platform filter; falls back to runtime ContextVar
            platform_user: Optional user filter; falls back to runtime ContextVar
            include_inactive: If True, also return soft-deleted memories.

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

        if not include_inactive:
            where_clauses.append("is_active = 1")

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
            "SELECT id, content, tags, session_id, created_at, platform, platform_user, "
            "is_active, deleted_at, deleted_reason, superseded_by, is_pinned, "
            "is_user_authored, last_recalled_at, is_global "
            f"FROM memory {where_str} "
            "ORDER BY created_at DESC LIMIT :limit"
        )

        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, params)
            rows = result.fetchall()
            return [self._row_to_memory(row) for row in rows]

    async def get(self, memory_id: str) -> Memory | None:
        """Get a memory by ID.

        Returns:
            The Memory, or None if not found.
        """
        sql = sa.text(
            "SELECT id, content, tags, session_id, created_at, platform, platform_user, "
            "is_active, deleted_at, deleted_reason, superseded_by, is_pinned, "
            "is_user_authored, last_recalled_at, is_global "
            "FROM memory WHERE id = :id"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"id": memory_id})
            row = result.fetchone()
            if row:
                return self._row_to_memory(row)
            return None

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

    async def soft_delete(
        self,
        memory_id: str,
        *,
        platform: str | None = None,
        platform_user: str | None = None,
        reason: str = "pruned",
        superseded_by: str | None = None,
    ) -> bool:
        """Soft-delete a memory by ID.

        Marks the memory inactive and records deletion metadata. Returns True
        if the memory was found and updated.
        """
        platform, platform_user = self._resolve_scope(platform, platform_user)

        where_clauses = ["id = :id"]
        params: dict[str, Any] = {
            "id": memory_id,
            "is_active": 0,
            "deleted_at": utcnow().isoformat(),
            "deleted_reason": reason,
            "superseded_by": superseded_by,
        }
        if platform is not None and platform_user is not None:
            where_clauses.append("platform = :platform AND platform_user = :platform_user")
            params["platform"] = platform
            params["platform_user"] = platform_user

        sql = sa.text(
            "UPDATE memory SET is_active = :is_active, deleted_at = :deleted_at, "
            "deleted_reason = :deleted_reason, superseded_by = :superseded_by "
            f"WHERE {' AND '.join(where_clauses)}"
        )

        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, params)
            await conn.commit()
            return result.rowcount > 0

    async def restore(
        self,
        memory_id: str,
        *,
        platform: str | None = None,
        platform_user: str | None = None,
    ) -> bool:
        """Restore a soft-deleted memory by ID.

        Clears inactive/deleted flags. Returns True if the memory was found
        and updated.
        """
        platform, platform_user = self._resolve_scope(platform, platform_user)

        where_clauses = ["id = :id"]
        params: dict[str, Any] = {
            "id": memory_id,
            "is_active": 1,
            "deleted_at": None,
            "deleted_reason": None,
            "superseded_by": None,
        }
        if platform is not None and platform_user is not None:
            where_clauses.append("platform = :platform AND platform_user = :platform_user")
            params["platform"] = platform
            params["platform_user"] = platform_user

        sql = sa.text(
            "UPDATE memory SET is_active = :is_active, deleted_at = :deleted_at, "
            "deleted_reason = :deleted_reason, superseded_by = :superseded_by "
            f"WHERE {' AND '.join(where_clauses)}"
        )

        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, params)
            await conn.commit()
            return result.rowcount > 0

    async def update(
        self,
        memory_id: str,
        *,
        content: str | None = None,
        tags: list[str] | None = None,
        platform: str | None = None,
        platform_user: str | None = None,
    ) -> bool:
        """Update content and/or tags of an active memory.

        Only active memories can be updated; soft-deleted rows are ignored.
        Returns True if the memory was found and updated.
        """
        platform, platform_user = self._resolve_scope(platform, platform_user)

        set_clauses: list[str] = []
        params: dict[str, Any] = {"id": memory_id, "is_active": 1}

        if content is not None:
            sanitized = self._sanitizer.sanitize(content)
            if sanitized.rejected:
                logger.warning(
                    "Memory update rejected by sanitizer: %s",
                    sanitized.reason,
                )
                return False
            set_clauses.append("content = :content")
            params["content"] = sanitized.content or content

        if tags is not None:
            set_clauses.append("tags = :tags")
            params["tags"] = "|".join(tags)

        if not set_clauses:
            return False

        where_clauses = ["id = :id", "is_active = :is_active"]
        if platform is not None and platform_user is not None:
            where_clauses.append("platform = :platform AND platform_user = :platform_user")
            params["platform"] = platform
            params["platform_user"] = platform_user

        sql = sa.text(
            f"UPDATE memory SET {', '.join(set_clauses)} WHERE {' AND '.join(where_clauses)}"
        )

        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, params)
            await conn.commit()
            return result.rowcount > 0

    async def pin(self, memory_id: str, pinned: bool = True) -> bool:
        """Set the pinned flag on a memory by ID."""
        sql = sa.text(
            "UPDATE memory SET is_pinned = :is_pinned WHERE id = :id"
        )
        params = {"id": memory_id, "is_pinned": 1 if pinned else 0}

        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, params)
            await conn.commit()
            return result.rowcount > 0

    async def mark_user_authored(self, memory_id: str) -> bool:
        """Mark a memory as user-authored by ID."""
        sql = sa.text(
            "UPDATE memory SET is_user_authored = 1 WHERE id = :id"
        )

        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"id": memory_id})
            await conn.commit()
            return result.rowcount > 0

    async def mark_recalled(self, memory_id: str) -> bool:
        """Set last_recalled_at to now for a memory by ID."""
        sql = sa.text(
            "UPDATE memory SET last_recalled_at = :now WHERE id = :id"
        )
        params = {"id": memory_id, "now": utcnow().isoformat()}

        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, params)
            await conn.commit()
            return result.rowcount > 0

    async def list_active_memories(
        self,
        tag: str | None = None,
        limit: int = 20,
        platform: str | None = None,
        platform_user: str | None = None,
    ) -> list[Memory]:
        """List active memories, optionally filtered by tag and user scope."""
        return await self.list_memories(
            tag=tag,
            limit=limit,
            platform=platform,
            platform_user=platform_user,
            include_inactive=False,
        )

    async def list_inactive_memories(
        self,
        tag: str | None = None,
        limit: int = 20,
        platform: str | None = None,
        platform_user: str | None = None,
    ) -> list[Memory]:
        """List soft-deleted memories within the retention window."""
        from datetime import timedelta

        platform, platform_user = self._resolve_scope(platform, platform_user)

        cutoff = (utcnow() - timedelta(days=self._config.retention_days)).isoformat()

        params: dict[str, Any] = {"limit": limit, "cutoff": cutoff}
        where_clauses: list[str] = ["is_active = 0", "deleted_at >= :cutoff"]

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
                params["p0"] = f"{tag}|%"
                params["p1"] = f"%|{tag}|%"
                params["p2"] = f"%|{tag}"

        if platform is not None and platform_user is not None:
            where_clauses.append("platform = :platform AND platform_user = :platform_user")
            params["platform"] = platform
            params["platform_user"] = platform_user

        where_str = "WHERE " + " AND ".join(where_clauses)

        sql = sa.text(
            "SELECT id, content, tags, session_id, created_at, platform, platform_user, "
            "is_active, deleted_at, deleted_reason, superseded_by, is_pinned, "
            "is_user_authored, last_recalled_at, is_global "
            f"FROM memory {where_str} "
            "ORDER BY deleted_at DESC LIMIT :limit"
        )

        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, params)
            rows = result.fetchall()
            return [self._row_to_memory(row) for row in rows]

    def _is_protected(self, memory: Memory) -> bool:
        """Return True when a memory should not be soft-deleted."""
        if memory.is_user_authored or memory.is_pinned:
            return True
        if memory.last_recalled_at is not None:
            age_days = (utcnow() - memory.last_recalled_at).days
            if age_days < self._config.recently_recalled_days:
                return True
        return False

    def is_protected(self, memory: Memory) -> bool:
        """Public helper: return True when a memory is in the protected set."""
        return self._is_protected(memory)

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

        def _parse_dt(value: Any) -> datetime | None:
            if value is None:
                return None
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                return datetime.fromisoformat(value)
            return None

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
            is_active=bool(row.is_active),
            deleted_at=_parse_dt(row.deleted_at),
            deleted_reason=row.deleted_reason,
            superseded_by=row.superseded_by,
            is_pinned=bool(row.is_pinned),
            is_user_authored=bool(row.is_user_authored),
            last_recalled_at=_parse_dt(row.last_recalled_at),
            is_global=bool(row.is_global),
        )
