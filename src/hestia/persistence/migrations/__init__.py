"""Lightweight, additive runtime migrations for Hestia's persistence layer.

Hestia does not (yet) use Alembic. The schema is defined declaratively in
``hestia.persistence.schema`` and applied via ``metadata.create_all`` for fresh
databases. For *existing* databases that pre-date a schema change, we apply
small idempotent migrations from this module on every ``Database.create_tables``
call. Each migration must be:

- **Idempotent**: safe to run repeatedly (use ``IF NOT EXISTS`` guards or
  pre-flight ``SELECT`` checks).
- **Additive only**: new tables, new columns, new indexes. Destructive
  schema changes (drops, type narrowing) are out of scope here and would
  warrant introducing Alembic.
- **Dialect-portable**: works on both SQLite and PostgreSQL, the two
  dialects ``Database`` supports today.

The list ``MIGRATIONS`` is the source of truth; new migrations are appended,
never re-ordered or removed. Each entry is a coroutine that takes an
``AsyncConnection`` already inside a transaction.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

Migration = Callable[[AsyncConnection], Awaitable[None]]


async def m001_sessions_active_unique(conn: AsyncConnection) -> None:
    """Add a partial unique index ensuring at most one ACTIVE session per user.

    Backs the TOCTOU-safe upsert in ``SessionStore.get_or_create_session``.
    Idempotent: ``CREATE UNIQUE INDEX IF NOT EXISTS`` is supported by both
    SQLite (>= 3.8.0) and PostgreSQL (>= 9.5).

    If a pre-existing database already contains duplicate ACTIVE rows for the
    same ``(platform, platform_user)`` pair, this index creation will fail.
    That indicates corruption from the prior race window and requires manual
    cleanup; we let the error surface rather than silently dropping rows.
    """
    # The WHERE predicate must match the persisted enum value exactly:
    # ``SessionState.ACTIVE.value == "active"`` (lowercase). See
    # ``schema.py`` and ``SessionStore._build_active_session_upsert``.
    await conn.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_sessions_active_user "
            "ON sessions (platform, platform_user) "
            "WHERE state = 'active'"
        )
    )


async def m002_session_handoffs(conn: AsyncConnection) -> None:
    """Add session_handoffs table for cross-session continuity.

    Idempotent: ``CREATE TABLE IF NOT EXISTS`` is supported by both
    SQLite (>= 3.3.0) and PostgreSQL (>= 9.1).
    """
    await conn.execute(
        sa.text(
            "CREATE TABLE IF NOT EXISTS session_handoffs ("
            "id TEXT PRIMARY KEY,"
            "previous_session_id TEXT NOT NULL,"
            "platform TEXT NOT NULL,"
            "platform_user TEXT NOT NULL,"
            "summary TEXT,"
            "key_messages TEXT,"
            "artifacts TEXT,"
            "created_at DATETIME NOT NULL"
            ")"
        )
    )
    await conn.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_handoffs_platform_user "
            "ON session_handoffs (platform, platform_user, created_at)"
        )
    )


async def m003_users_and_rooms(conn: AsyncConnection) -> None:
    """Add users, user_identities, rooms, and room_members tables."""
    await conn.execute(sa.text(
        "CREATE TABLE IF NOT EXISTS users ("
        "id TEXT PRIMARY KEY,"
        "display_name TEXT NOT NULL,"
        "role TEXT NOT NULL DEFAULT 'user',"
        "trust_preset TEXT,"
        "notes TEXT,"
        "created_at DATETIME NOT NULL,"
        "updated_at DATETIME NOT NULL"
        ")"
    ))
    await conn.execute(sa.text(
        "CREATE TABLE IF NOT EXISTS user_identities ("
        "user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
        "platform TEXT NOT NULL,"
        "platform_user TEXT NOT NULL,"
        "verified INTEGER NOT NULL DEFAULT 0,"
        "created_at DATETIME NOT NULL,"
        "PRIMARY KEY (platform, platform_user)"
        ")"
    ))
    await conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_user_identities_user ON user_identities(user_id)"
    ))
    await conn.execute(sa.text(
        "CREATE TABLE IF NOT EXISTS rooms ("
        "id TEXT PRIMARY KEY,"
        "platform TEXT NOT NULL,"
        "platform_room_id TEXT NOT NULL,"
        "display_name TEXT,"
        "created_at DATETIME NOT NULL,"
        "UNIQUE (platform, platform_room_id)"
        ")"
    ))
    await conn.execute(sa.text(
        "CREATE TABLE IF NOT EXISTS room_members ("
        "room_id TEXT NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,"
        "user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
        "joined_at DATETIME NOT NULL,"
        "PRIMARY KEY (room_id, user_id)"
        ")"
    ))


async def m004_messages_correction(conn: AsyncConnection) -> None:
    """Add correction flag to messages table.

    Idempotent: checks whether the column already exists before adding it.
    SQLite does not support ``ALTER TABLE IF NOT EXISTS ADD COLUMN``,
    so we inspect the table info first.
    """
    dialect = conn.dialect.name
    if dialect == "sqlite":
        result = await conn.execute(
            sa.text("SELECT 1 FROM pragma_table_info('messages') WHERE name = 'correction'")
        )
        has_column = result.scalar() is not None
    else:
        result = await conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'messages' AND column_name = 'correction'"
            )
        )
        has_column = result.scalar() is not None

    if not has_column:
        await conn.execute(
            sa.text("ALTER TABLE messages ADD COLUMN correction INTEGER NOT NULL DEFAULT 0")
        )


async def m005_capability_events(conn: AsyncConnection) -> None:
    """Add capability_events audit table for the trust/capability gate."""
    await conn.execute(
        sa.text(
            "CREATE TABLE IF NOT EXISTS capability_events ("
            "id TEXT PRIMARY KEY,"
            "tool_name TEXT NOT NULL,"
            "arguments_json TEXT NOT NULL,"
            "channel TEXT NOT NULL,"
            "actor_platform TEXT NOT NULL,"
            "actor_platform_user TEXT NOT NULL,"
            "source_workflow_id TEXT,"
            "source_trigger_id TEXT,"
            "decision TEXT NOT NULL,"
            "reason TEXT NOT NULL,"
            "injection_flagged INTEGER NOT NULL DEFAULT 0,"
            "created_at DATETIME NOT NULL"
            ")"
        )
    )
    await conn.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_capability_events_created "
            "ON capability_events (created_at)"
        )
    )
    await conn.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_capability_events_actor "
            "ON capability_events (actor_platform, actor_platform_user, created_at)"
        )
    )


async def m006_workflow_allow_list(conn: AsyncConnection) -> None:
    """Add allow_listed_tools column to workflows table."""
    dialect = conn.dialect.name
    if dialect == "sqlite":
        result = await conn.execute(
            sa.text(
                "SELECT name FROM pragma_table_info('workflows') WHERE name = 'allow_listed_tools'"
            )
        )
        has_column = result.fetchone() is not None
    else:
        # BUG-009: pragma_table_info is SQLite-only; PostgreSQL startup used
        # to crash here. Mirror m007's information_schema fallback.
        result = await conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'workflows' AND column_name = 'allow_listed_tools'"
            )
        )
        has_column = result.scalar() is not None

    if not has_column:
        await conn.execute(
            sa.text(
                "ALTER TABLE workflows ADD COLUMN allow_listed_tools TEXT NOT NULL DEFAULT '[]'"
            )
        )


async def m007_scheduled_task_type(conn: AsyncConnection) -> None:
    """Add task_type column to scheduled_tasks table."""
    dialect = conn.dialect.name
    if dialect == "sqlite":
        result = await conn.execute(
            sa.text(
                "SELECT 1 FROM pragma_table_info('scheduled_tasks') WHERE name = 'task_type'"
            )
        )
        has_column = result.scalar() is not None
    else:
        result = await conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'scheduled_tasks' AND column_name = 'task_type'"
            )
        )
        has_column = result.scalar() is not None

    if not has_column:
        await conn.execute(
            sa.text(
                "ALTER TABLE scheduled_tasks ADD COLUMN task_type TEXT NOT NULL DEFAULT 'chat'"
            )
        )


async def m008_compaction_archive(conn: AsyncConnection) -> None:
    """Add compaction_archive table for recoverable /compact history.

    Archives every message replaced by a compaction so the original history
    remains recoverable. Indexed by session for efficient retrieval.
    """
    await conn.execute(
        sa.text(
            "CREATE TABLE IF NOT EXISTS compaction_archive ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "session_id TEXT NOT NULL,"
            "original_idx INTEGER NOT NULL,"
            "role TEXT NOT NULL,"
            "content TEXT NOT NULL,"
            "tool_calls TEXT,"
            "tool_call_id TEXT,"
            "reasoning_content TEXT,"
            "is_handoff INTEGER NOT NULL DEFAULT 0,"
            "correction INTEGER NOT NULL DEFAULT 0,"
            "created_at DATETIME NOT NULL,"
            "compacted_at DATETIME NOT NULL"
            ")"
        )
    )
    await conn.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_compaction_archive_session "
            "ON compaction_archive (session_id, original_idx)"
        )
    )


async def m009_hot_path_indexes(conn: AsyncConnection) -> None:
    """PERF-005: indexes for the hottest query patterns.

    Every context build runs ``SELECT ... WHERE session_id = ? ORDER BY idx``
    against messages and every append computes ``max(idx)``; without an
    index each is a full scan of the largest table. Sessions are ordered by
    last_active_at for staleness/LLU queries.
    """
    await conn.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_messages_session_idx "
            "ON messages (session_id, idx)"
        )
    )
    await conn.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_sessions_last_active "
            "ON sessions (last_active_at)"
        )
    )


async def m010_execution_is_test(conn: AsyncConnection) -> None:
    """BUG-041: flag test-run executions so aggregates exclude them."""
    dialect = conn.dialect.name
    if dialect == "sqlite":
        result = await conn.execute(
            sa.text(
                "SELECT name FROM pragma_table_info('workflow_executions') WHERE name = 'is_test'"
            )
        )
        has_column = result.fetchone() is not None
    else:
        result = await conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'workflow_executions' AND column_name = 'is_test'"
            )
        )
        has_column = result.scalar() is not None
    if not has_column:
        default = "0" if dialect == "sqlite" else "FALSE"
        await conn.execute(
            sa.text(
                "ALTER TABLE workflow_executions "
                f"ADD COLUMN is_test BOOLEAN NOT NULL DEFAULT {default}"
            )
        )


MIGRATIONS: list[Migration] = [
    m001_sessions_active_unique,
    m002_session_handoffs,
    m003_users_and_rooms,
    m004_messages_correction,
    m005_capability_events,
    m006_workflow_allow_list,
    m007_scheduled_task_type,
    m008_compaction_archive,
    m009_hot_path_indexes,
]


async def apply_runtime_migrations(engine: AsyncEngine) -> None:
    """Run all migrations in order. Safe to call repeatedly."""
    async with engine.begin() as conn:
        for migration in MIGRATIONS:
            await migration(conn)


__all__ = ["MIGRATIONS", "apply_runtime_migrations", "m001_sessions_active_unique"]
