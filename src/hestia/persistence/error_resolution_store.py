"""Error resolution persistence layer."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import bindparam

from hestia.core.clock import utcnow

if TYPE_CHECKING:
    from hestia.persistence.db import Database


class ErrorResolutionStore:
    """Store for persisting error resolution status.

    Replaces in-memory _resolved_ids / _ignored_ids sets so that
    resolution state survives server restarts.
    """

    def __init__(self, db: Database) -> None:
        """Initialize with a Database instance."""
        self._db = db

    async def get_status(self, error_id: str) -> str | None:
        """Return the resolution status for an error, or None."""
        sql = sa.text(
            "SELECT status FROM error_resolutions WHERE error_id = :error_id"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"error_id": error_id})
            row = result.fetchone()
            return row[0] if row else None

    async def set_status(
        self, error_id: str, status: str, resolved_by: str | None = None
    ) -> None:
        """Insert or update the resolution status for an error."""
        sql = sa.text(
            "INSERT INTO error_resolutions (error_id, status, resolved_at, resolved_by) "
            "VALUES (:error_id, :status, :resolved_at, :resolved_by) "
            "ON CONFLICT (error_id) DO UPDATE SET "
            "status = EXCLUDED.status, "
            "resolved_at = EXCLUDED.resolved_at, "
            "resolved_by = EXCLUDED.resolved_by"
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(
                sql,
                {
                    "error_id": error_id,
                    "status": status,
                    "resolved_at": utcnow(),
                    "resolved_by": resolved_by,
                },
            )
            await conn.commit()

    async def list_statuses(self, error_ids: list[str]) -> dict[str, str]:
        """Batch-fetch resolution statuses for the given error IDs."""
        if not error_ids:
            return {}
        sql = sa.text(
            "SELECT error_id, status FROM error_resolutions "
            "WHERE error_id IN :error_ids"
        ).bindparams(bindparam("error_ids", expanding=True))
        async with self._db.engine.connect() as conn:
            result = await conn.execute(
                sql, {"error_ids": error_ids}
            )
            rows = result.fetchall()
            return {row[0]: row[1] for row in rows}

    async def clear_old(self, days: int = 30) -> int:
        """Remove resolution entries older than N days. Returns count deleted."""
        cutoff = utcnow() - timedelta(days=days)
        sql = sa.text(
            "DELETE FROM error_resolutions WHERE resolved_at < :cutoff"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"cutoff": cutoff})
            await conn.commit()
            return result.rowcount
