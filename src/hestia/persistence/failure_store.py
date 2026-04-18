"""Failure tracking persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa

if TYPE_CHECKING:
    from hestia.persistence.db import Database


@dataclass
class FailureBundle:
    """Structured record of a turn failure.

    Captures failure classification, context, and metadata for analytics
    and future self-healing features.
    """

    id: str
    session_id: str
    turn_id: str
    failure_class: str
    severity: str
    error_message: str
    tool_chain: str  # JSON list of tool names called during the turn
    created_at: datetime
    # Enriched fields (Phase 11.2)
    request_summary: str | None = None  # first 200 chars of user message
    policy_snapshot: str | None = None  # JSON: allowed tools, reasoning budget, etc.
    slot_snapshot: str | None = None  # JSON: slot_id, session temperature
    trace_id: str | None = None  # link to trace record


class FailureStore:
    """Store for failure records.

    Uses raw DDL for table creation (consistent with MemoryStore pattern).
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create_table(self) -> None:
        """Create the failure_bundles table if it doesn't exist."""
        ddl = """
        CREATE TABLE IF NOT EXISTS failure_bundles (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            turn_id TEXT NOT NULL,
            failure_class TEXT NOT NULL,
            severity TEXT NOT NULL,
            error_message TEXT NOT NULL,
            tool_chain TEXT NOT NULL,
            created_at TEXT NOT NULL,
            request_summary TEXT,
            policy_snapshot TEXT,
            slot_snapshot TEXT,
            trace_id TEXT
        )
        """
        idx_class = (
            "CREATE INDEX IF NOT EXISTS idx_failure_bundles_class ON failure_bundles(failure_class)"
        )
        idx_created = (
            "CREATE INDEX IF NOT EXISTS idx_failure_bundles_created ON failure_bundles(created_at)"
        )

        async with self._db.engine.connect() as conn:
            await conn.execute(sa.text(ddl))
            await conn.execute(sa.text(idx_class))
            await conn.execute(sa.text(idx_created))
            await conn.commit()

    async def record(self, bundle: FailureBundle) -> None:
        """Record a failure bundle."""
        sql = sa.text(
            "INSERT INTO failure_bundles (id, session_id, turn_id, failure_class, "
            "severity, error_message, tool_chain, created_at, request_summary, "
            "policy_snapshot, slot_snapshot, trace_id) "
            "VALUES (:id, :session_id, :turn_id, :failure_class, :severity, "
            ":error_message, :tool_chain, :created_at, :request_summary, "
            ":policy_snapshot, :slot_snapshot, :trace_id)"
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(
                sql,
                {
                    "id": bundle.id,
                    "session_id": bundle.session_id,
                    "turn_id": bundle.turn_id,
                    "failure_class": bundle.failure_class,
                    "severity": bundle.severity,
                    "error_message": bundle.error_message,
                    "tool_chain": bundle.tool_chain,
                    "created_at": bundle.created_at.isoformat(),
                    "request_summary": bundle.request_summary,
                    "policy_snapshot": bundle.policy_snapshot,
                    "slot_snapshot": bundle.slot_snapshot,
                    "trace_id": bundle.trace_id,
                },
            )
            await conn.commit()

    async def list_recent(
        self, limit: int = 20, failure_class: str | None = None
    ) -> list[FailureBundle]:
        """List recent failure bundles with optional filter."""
        if failure_class:
            sql = sa.text(
                "SELECT id, session_id, turn_id, failure_class, severity, "
                "error_message, tool_chain, created_at, request_summary, "
                "policy_snapshot, slot_snapshot, trace_id "
                "FROM failure_bundles WHERE failure_class = :fc "
                "ORDER BY created_at DESC LIMIT :limit"
            )
            params = {"fc": failure_class, "limit": limit}
        else:
            sql = sa.text(
                "SELECT id, session_id, turn_id, failure_class, severity, "
                "error_message, tool_chain, created_at, request_summary, "
                "policy_snapshot, slot_snapshot, trace_id "
                "FROM failure_bundles "
                "ORDER BY created_at DESC LIMIT :limit"
            )
            params = {"limit": limit}

        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, params)
            rows = result.fetchall()
            return [self._row_to_bundle(row) for row in rows]

    async def count_by_class(self, since: datetime | None = None) -> dict[str, int]:
        """Count failures by class, optionally since a specific time."""
        if since:
            sql = sa.text(
                "SELECT failure_class, COUNT(*) FROM failure_bundles "
                "WHERE created_at >= :since GROUP BY failure_class"
            )
            params = {"since": since.isoformat()}
        else:
            sql = sa.text(
                "SELECT failure_class, COUNT(*) FROM failure_bundles GROUP BY failure_class"
            )
            params = {}

        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, params)
            rows = result.fetchall()
            return {row[0]: row[1] for row in rows}

    def _row_to_bundle(self, row: Any) -> FailureBundle:
        """Convert a database row to a FailureBundle."""
        created_at = row.created_at
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        return FailureBundle(
            id=row.id,
            session_id=row.session_id,
            turn_id=row.turn_id,
            failure_class=row.failure_class,
            severity=row.severity,
            error_message=row.error_message,
            tool_chain=row.tool_chain,
            created_at=created_at,
            request_summary=row.request_summary if hasattr(row, "request_summary") else None,
            policy_snapshot=row.policy_snapshot if hasattr(row, "policy_snapshot") else None,
            slot_snapshot=row.slot_snapshot if hasattr(row, "slot_snapshot") else None,
            trace_id=row.trace_id if hasattr(row, "trace_id") else None,
        )
