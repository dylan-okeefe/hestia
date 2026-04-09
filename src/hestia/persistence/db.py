"""Database connection and management."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from hestia.errors import PersistenceError
from hestia.persistence.schema import metadata


class Database:
    """Async database connection manager using SQLAlchemy Core."""

    def __init__(self, url: str) -> None:
        """Initialize with a database URL.

        Args:
            url: SQLAlchemy async URL, e.g.:
                 sqlite+aiosqlite:///path/to/db.db
                 postgresql+asyncpg://user:pw@host:5432/db
        """
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
        """Create all tables from schema."""
        if self._engine is None:
            raise PersistenceError("Database not connected. Call connect() first.")
        async with self._engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

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


import sqlalchemy as sa  # noqa: E402
