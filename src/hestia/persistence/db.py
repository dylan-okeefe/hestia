"""Database connection and management."""

from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from hestia.errors import PersistenceError
from hestia.persistence.schema import metadata


def _asyncpg_available() -> bool:
    """Check if asyncpg is installed."""
    try:
        import asyncpg  # noqa: F401
        return True
    except ImportError:
        return False


class Database:
    """Async database connection manager using SQLAlchemy Core."""

    def __init__(self, url: str) -> None:
        """Initialize with a database URL.

        Args:
            url: SQLAlchemy async URL, e.g.:
                 sqlite+aiosqlite:///path/to/db.db
                 postgresql+asyncpg://user:pw@host:5432/db
        """
        if url.startswith("postgresql") and not _asyncpg_available():
            raise ImportError(
                "PostgreSQL support requires the 'postgres' extra: "
                "pip install hestia[postgres]"
            )
        self._url = url
        self._engine: AsyncEngine | None = None

    async def connect(self) -> None:
        """Create engine and verify connectivity."""
        self._engine = create_async_engine(
            self._url,
            echo=False,
            future=True,
        )
        # Verify connection
        async with self._engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))

    async def close(self) -> None:
        """Dispose the engine."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None

    @property
    def engine(self) -> AsyncEngine:
        """Get the async engine."""
        if self._engine is None:
            raise PersistenceError("Database not connected. Call connect() first.")
        return self._engine

    async def create_tables(self) -> None:
        """Create all tables from schema, then apply additive runtime migrations.

        ``metadata.create_all`` covers fresh databases. Existing databases that
        pre-date a schema change pick up additive migrations (new indexes,
        columns) via ``apply_runtime_migrations``, which is idempotent.
        """
        if self._engine is None:
            raise PersistenceError("Database not connected. Call connect() first.")
        async with self._engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
        # Local import keeps the migrations module a leaf and avoids any chance
        # of an import cycle with schema.py via metadata reflection helpers.
        from hestia.persistence.migrations import apply_runtime_migrations

        await apply_runtime_migrations(self._engine)

    async def execute(self, query: Any) -> Any:
        """Execute a query and return result.

        Thin wrapper for tests and simple queries.
        """
        if self._engine is None:
            raise PersistenceError("Database not connected. Call connect() first.")
        async with self._engine.connect() as conn:
            result = await conn.execute(query)
            await conn.commit()
            return result


