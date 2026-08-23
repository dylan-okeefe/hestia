"""Persistence for memory maintenance trace records."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Any

import sqlalchemy as sa

from hestia.core.clock import utcnow
from hestia.memory.maintenance.trace import MaintenanceAction
from hestia.persistence.db import Database


class MaintenanceTraceStore:
    """Store for maintenance action traces.

    Backed by a regular SQLite table (not FTS) declared in
    :mod:`hestia.persistence.schema`. Callers that predate the consolidated
    schema can rely on :meth:`create_table` to create the table idempotently.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create_table(self) -> None:
        """Create the maintenance_trace table if it does not exist."""
        ddl = """
        CREATE TABLE IF NOT EXISTS maintenance_trace (
            id TEXT PRIMARY KEY,
            action TEXT NOT NULL,
            identity_platform TEXT,
            identity_user TEXT,
            winner_memory_id TEXT,
            loser_memory_ids TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL,
            undoable_until TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '{}'
        )
        """
        async with self._db.engine.connect() as conn:
            await conn.execute(sa.text(ddl))
            await conn.execute(
                sa.text(
                    "CREATE INDEX IF NOT EXISTS idx_maintenance_trace_user "
                    "ON maintenance_trace (identity_platform, identity_user, created_at)"
                )
            )
            await conn.execute(
                sa.text(
                    "CREATE INDEX IF NOT EXISTS idx_maintenance_trace_created "
                    "ON maintenance_trace (created_at)"
                )
            )
            await conn.commit()

    async def record(self, action: MaintenanceAction) -> None:
        """Persist a maintenance action."""
        sql = sa.text(
            "INSERT INTO maintenance_trace (id, action, identity_platform, identity_user, "
            "winner_memory_id, loser_memory_ids, reason, created_at, undoable_until, details) "
            "VALUES (:id, :action, :identity_platform, :identity_user, :winner_memory_id, "
            ":loser_memory_ids, :reason, :created_at, :undoable_until, :details)"
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(
                sql,
                {
                    "id": action.id,
                    "action": action.action,
                    "identity_platform": action.identity_platform,
                    "identity_user": action.identity_user,
                    "winner_memory_id": action.winner_memory_id,
                    "loser_memory_ids": json.dumps(action.loser_memory_ids),
                    "reason": action.reason,
                    "created_at": action.created_at.isoformat(),
                    "undoable_until": action.undoable_until.isoformat(),
                    "details": json.dumps(action.details),
                },
            )
            await conn.commit()

    async def list_recent(
        self,
        platform: str | None = None,
        platform_user: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[MaintenanceAction]:
        """List recent maintenance actions with optional filters."""
        clauses: list[str] = []
        params: dict[str, Any] = {"limit": limit}

        if platform is not None:
            clauses.append("identity_platform = :platform")
            params["platform"] = platform
        if platform_user is not None:
            clauses.append("identity_user = :platform_user")
            params["platform_user"] = platform_user
        if since is not None:
            clauses.append("created_at >= :since")
            params["since"] = since.isoformat()

        base_sql = (
            "SELECT id, action, identity_platform, identity_user, winner_memory_id, "
            "loser_memory_ids, reason, created_at, undoable_until, details "
            "FROM maintenance_trace"
        )
        if clauses:
            base_sql += " WHERE " + " AND ".join(clauses)
        base_sql += " ORDER BY created_at DESC LIMIT :limit"

        sql = sa.text(base_sql)
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, params)
            rows = result.fetchall()
            return [self._row_to_action(row) for row in rows]

    async def get(self, action_id: str) -> MaintenanceAction | None:
        """Get a maintenance action by ID."""
        sql = sa.text(
            "SELECT id, action, identity_platform, identity_user, winner_memory_id, "
            "loser_memory_ids, reason, created_at, undoable_until, details "
            "FROM maintenance_trace WHERE id = :id"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"id": action_id})
            row = result.fetchone()
            if row is None:
                return None
            return self._row_to_action(row)

    async def clear_old(self, days: int) -> int:
        """Delete maintenance traces older than *days*.

        The undo window (undoable_until, default 7 days) is the only consumer
        of old traces; beyond it the rows — which embed full merged-content
        blobs — grow without bound (BUG-075). Returns the number deleted.
        """
        cutoff = (utcnow() - timedelta(days=days)).isoformat()
        sql = sa.text("DELETE FROM maintenance_trace WHERE created_at < :cutoff")
        async with self._db.engine.begin() as conn:
            result = await conn.execute(sql, {"cutoff": cutoff})
            return result.rowcount or 0

    def _row_to_action(self, row: Any) -> MaintenanceAction:
        """Convert a database row to a MaintenanceAction."""
        created_at = row.created_at
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        undoable_until = row.undoable_until
        if isinstance(undoable_until, str):
            undoable_until = datetime.fromisoformat(undoable_until)
        return MaintenanceAction(
            id=row.id,
            action=row.action,
            identity_platform=row.identity_platform,
            identity_user=row.identity_user,
            winner_memory_id=row.winner_memory_id,
            loser_memory_ids=json.loads(row.loser_memory_ids) if row.loser_memory_ids else [],
            reason=row.reason,
            created_at=created_at,
            undoable_until=undoable_until,
            details=json.loads(row.details) if row.details else {},
        )

    @staticmethod
    def generate_id() -> str:
        """Generate a unique maintenance action ID."""
        return f"maint_{uuid.uuid4().hex[:16]}"
