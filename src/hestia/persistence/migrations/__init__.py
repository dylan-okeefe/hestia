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


MIGRATIONS: list[Migration] = [
    m001_sessions_active_unique,
]


async def apply_runtime_migrations(engine: AsyncEngine) -> None:
    """Run all migrations in order. Safe to call repeatedly."""
    async with engine.begin() as conn:
        for migration in MIGRATIONS:
            await migration(conn)


__all__ = ["MIGRATIONS", "apply_runtime_migrations", "m001_sessions_active_unique"]
