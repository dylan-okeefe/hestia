"""Trace persistence for recording structured traces of unit of work.

This is the foundation for analysis features — you can't analyze what you don't record.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import sqlalchemy as sa

from hestia.core.clock import utcnow

if TYPE_CHECKING:
    from hestia.persistence.db import Database


@dataclass
class TraceRecord:
    """Structured record of a turn execution.

    Captures metadata, timing, token usage, and outcome for analytics.
    This complements the turns table which is optimized for state machine correctness.
    """

    id: str
    session_id: str
    turn_id: str
    started_at: datetime
    ended_at: datetime | None
    user_input_summary: str  # first 200 chars of user message
    tools_called: list[str]  # tool names in order
    tool_call_count: int
    delegated: bool
    outcome: str  # "success", "partial", "failed"
    artifact_handles: list[str]
    prompt_tokens: int | None
    completion_tokens: int | None
    reasoning_tokens: int | None
    total_duration_ms: int | None


class TraceStore:
    """Store for execution traces.

    The ``traces`` and ``egress_events`` tables are declared in
    :mod:`hestia.persistence.schema` and created by
    :meth:`Database.create_tables`. :meth:`create_table` here is kept as a
    no-op shim for backward compatibility with callers that predate the DDL
    consolidation. New code should rely on
    ``Database.create_tables`` exclusively.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create_table(self) -> None:
        """Deprecated no-op kept for call-site compatibility.

        Schema creation now lives in
        :meth:`hestia.persistence.db.Database.create_tables` via the shared
        SQLAlchemy metadata. The duplicated raw DDL that lived here was the
        source of drift flagged by the Copilot audit.
        """
        return None

    async def record(self, trace: TraceRecord) -> None:
        """Persist a trace record."""
        sql = sa.text(
            "INSERT INTO traces (id, session_id, turn_id, started_at, ended_at, "
            "user_input_summary, tools_called, tool_call_count, delegated, outcome, "
            "artifact_handles, prompt_tokens, completion_tokens, reasoning_tokens, "
            "total_duration_ms) "
            "VALUES (:id, :session_id, :turn_id, :started_at, :ended_at, "
            ":user_input_summary, :tools_called, :tool_call_count, :delegated, :outcome, "
            ":artifact_handles, :prompt_tokens, :completion_tokens, :reasoning_tokens, "
            ":total_duration_ms)"
        )

        async with self._db.engine.connect() as conn:
            await conn.execute(
                sql,
                {
                    "id": trace.id,
                    "session_id": trace.session_id,
                    "turn_id": trace.turn_id,
                    "started_at": trace.started_at.isoformat(),
                    "ended_at": trace.ended_at.isoformat() if trace.ended_at else None,
                    "user_input_summary": trace.user_input_summary,
                    "tools_called": json.dumps(trace.tools_called),
                    "tool_call_count": trace.tool_call_count,
                    "delegated": 1 if trace.delegated else 0,
                    "outcome": trace.outcome,
                    "artifact_handles": json.dumps(trace.artifact_handles),
                    "prompt_tokens": trace.prompt_tokens,
                    "completion_tokens": trace.completion_tokens,
                    "reasoning_tokens": trace.reasoning_tokens,
                    "total_duration_ms": trace.total_duration_ms,
                },
            )
            await conn.commit()

    async def list_recent(
        self, limit: int = 20, outcome: str | None = None
    ) -> list[TraceRecord]:
        """List recent traces with optional outcome filter."""
        if outcome:
            sql = sa.text(
                "SELECT id, session_id, turn_id, started_at, ended_at, "
                "user_input_summary, tools_called, tool_call_count, delegated, outcome, "
                "artifact_handles, prompt_tokens, completion_tokens, reasoning_tokens, "
                "total_duration_ms "
                "FROM traces WHERE outcome = :outcome "
                "ORDER BY started_at DESC LIMIT :limit"
            )
            params = {"outcome": outcome, "limit": limit}
        else:
            sql = sa.text(
                "SELECT id, session_id, turn_id, started_at, ended_at, "
                "user_input_summary, tools_called, tool_call_count, delegated, outcome, "
                "artifact_handles, prompt_tokens, completion_tokens, reasoning_tokens, "
                "total_duration_ms "
                "FROM traces ORDER BY started_at DESC LIMIT :limit"
            )
            params = {"limit": limit}

        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, params)
            rows = result.fetchall()
            return [self._row_to_trace(row) for row in rows]

    async def get_by_turn(self, turn_id: str) -> TraceRecord | None:
        """Get the trace record for a specific turn."""
        sql = sa.text(
            "SELECT id, session_id, turn_id, started_at, ended_at, "
            "user_input_summary, tools_called, tool_call_count, delegated, outcome, "
            "artifact_handles, prompt_tokens, completion_tokens, reasoning_tokens, "
            "total_duration_ms "
            "FROM traces WHERE turn_id = :turn_id"
        )

        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"turn_id": turn_id})
            row = result.fetchone()
            if row:
                return self._row_to_trace(row)
            return None

    async def count_by_outcome(self, since: datetime | None = None) -> dict[str, int]:
        """Count traces by outcome, optionally since a specific time."""
        if since:
            sql = sa.text(
                "SELECT outcome, COUNT(*) FROM traces "
                "WHERE started_at >= :since GROUP BY outcome"
            )
            params = {"since": since.isoformat()}
        else:
            sql = sa.text("SELECT outcome, COUNT(*) FROM traces GROUP BY outcome")
            params = {}

        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, params)
            rows = result.fetchall()
            return {row[0]: row[1] for row in rows}

    async def record_egress(
        self,
        session_id: str,
        url: str,
        status: int | None,
        size: int | None,
    ) -> None:
        """Persist an egress event.

        Best-effort: never raises.
        """
        try:
            domain = urlparse(url).hostname or "unknown"
        except Exception:
            domain = "unknown"

        sql = sa.text(
            "INSERT INTO egress_events (id, session_id, url, domain, status, size, created_at) "
            "VALUES (:id, :session_id, :url, :domain, :status, :size, :created_at)"
        )

        async with self._db.engine.connect() as conn:
            await conn.execute(
                sql,
                {
                    "id": str(uuid.uuid4()),
                    "session_id": session_id,
                    "url": url,
                    "domain": domain,
                    "status": status,
                    "size": size,
                    "created_at": utcnow().isoformat(),
                },
            )
            await conn.commit()

    async def egress_summary(
        self,
        since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Return domain-level egress aggregation.

        Each row contains:
        - domain
        - total_requests
        - failure_count (status is NULL or status >= 400)
        """
        if since:
            sql = sa.text(
                "SELECT domain, COUNT(*) as total_requests, "
                "SUM(CASE WHEN status IS NULL OR status >= 400 THEN 1 ELSE 0 END) as failure_count "
                "FROM egress_events WHERE created_at >= :since "
                "GROUP BY domain ORDER BY total_requests DESC"
            )
            params = {"since": since.isoformat()}
        else:
            sql = sa.text(
                "SELECT domain, COUNT(*) as total_requests, "
                "SUM(CASE WHEN status IS NULL OR status >= 400 THEN 1 ELSE 0 END) as failure_count "
                "FROM egress_events GROUP BY domain ORDER BY total_requests DESC"
            )
            params = {}

        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, params)
            rows = result.fetchall()
            return [
                {
                    "domain": row.domain,
                    "total_requests": row.total_requests,
                    "failure_count": row.failure_count,
                }
                for row in rows
            ]

    def _row_to_trace(self, row: Any) -> TraceRecord:
        """Convert a database row to a TraceRecord."""
        started_at = row.started_at
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at)

        ended_at = row.ended_at
        if isinstance(ended_at, str):
            ended_at = datetime.fromisoformat(ended_at)

        tools_called = json.loads(row.tools_called) if row.tools_called else []
        artifact_handles = json.loads(row.artifact_handles) if row.artifact_handles else []

        return TraceRecord(
            id=row.id,
            session_id=row.session_id,
            turn_id=row.turn_id,
            started_at=started_at,
            ended_at=ended_at,
            user_input_summary=row.user_input_summary,
            tools_called=tools_called,
            tool_call_count=row.tool_call_count,
            delegated=bool(row.delegated),
            outcome=row.outcome,
            artifact_handles=artifact_handles,
            prompt_tokens=row.prompt_tokens,
            completion_tokens=row.completion_tokens,
            reasoning_tokens=row.reasoning_tokens,
            total_duration_ms=row.total_duration_ms,
        )
