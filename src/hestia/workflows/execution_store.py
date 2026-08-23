"""Workflow execution persistence layer."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any

import sqlalchemy as sa

from hestia.core.clock import utcnow
from hestia.persistence.db import Database
from hestia.persistence.schema import workflow_executions

from .models import ExecutionResult


class ExecutionStore:
    """Typed CRUD wrapper for workflow execution persistence."""

    def __init__(self, db: Database) -> None:
        """Initialize with a Database instance."""
        self._db = db

    async def create_tables(self) -> None:
        """Create the workflow_executions table if it does not already exist."""
        async with self._db.engine.begin() as conn:
            await conn.run_sync(workflow_executions.create, checkfirst=True)

    async def start_execution(
        self,
        workflow_id: str,
        version: int,
        trigger_payload: Any,
        *,
        is_test: bool = False,
    ) -> str:
        """Create a RUNNING execution row upfront (BUG-036).

        Previously nothing was persisted until the whole graph finished, so a
        crash mid-run left zero trace of the attempt. The returned ID is
        passed to :meth:`save_execution` to finalize the row.
        """
        execution_id = str(uuid.uuid4())
        values: dict[str, Any] = {
            "id": execution_id,
            "workflow_id": workflow_id,
            "version": version,
            "status": "running",
            "trigger_payload": json.dumps(trigger_payload) if trigger_payload is not None else "{}",
            "node_results": "[]",
            "total_elapsed_ms": 0,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "is_test": 1 if is_test else 0,
            "created_at": utcnow(),
        }
        async with self._db.engine.connect() as conn:
            await conn.execute(sa.insert(workflow_executions).values(**values))
            await conn.commit()
        return execution_id

    async def fail_stale_running(self, *, older_than_minutes: int = 60) -> int:
        """Mark RUNNING executions older than the cutoff as failed (BUG-036)."""
        cutoff = utcnow() - timedelta(minutes=older_than_minutes)
        sql = sa.text(
            "UPDATE workflow_executions SET status = 'failed', "
            "node_results = '[{\"node_id\": \"\", \"status\": \"failed\", "
            "\"error\": \"Execution interrupted by restart or crash\"}]' "
            "WHERE status = 'running' AND created_at < :cutoff"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"cutoff": cutoff})
            await conn.commit()
            return result.rowcount or 0

    async def save_execution(
        self,
        result: ExecutionResult,
        workflow_id: str,
        version: int,
        trigger_payload: Any,
        *,
        execution_id: str | None = None,
        is_test: bool = False,
    ) -> str:
        """Save an execution result and return the execution ID.

        When *execution_id* refers to an existing RUNNING row it is updated
        in place; otherwise a new row is inserted.
        """
        if execution_id is None:
            execution_id = str(uuid.uuid4())
        node_results_json = json.dumps(
            [
                {
                    "node_id": nr.node_id,
                    "status": nr.status,
                    "output": nr.output,
                    "error": nr.error,
                    "elapsed_ms": nr.elapsed_ms,
                    "prompt_tokens": nr.prompt_tokens,
                    "completion_tokens": nr.completion_tokens,
                }
                for nr in result.node_results
            ]
        )

        values: dict[str, Any] = {
            "id": execution_id,
            "workflow_id": workflow_id,
            "version": version,
            "status": result.status,
            "trigger_payload": json.dumps(trigger_payload) if trigger_payload is not None else "{}",
            "node_results": node_results_json,
            "total_elapsed_ms": result.total_elapsed_ms,
            "total_prompt_tokens": result.total_prompt_tokens,
            "total_completion_tokens": result.total_completion_tokens,
            "is_test": 1 if is_test else 0,
            "created_at": utcnow(),
        }

        async with self._db.engine.begin() as conn:
            if execution_id is not None and await self._exists(conn, execution_id):
                values.pop("id", None)
                values.pop("created_at", None)
                await conn.execute(
                    workflow_executions.update()
                    .where(workflow_executions.c.id == execution_id)
                    .values(**values)
                )
            else:
                values["id"] = execution_id
                await conn.execute(sa.insert(workflow_executions).values(**values))

        return execution_id

    @staticmethod
    async def _exists(conn: Any, execution_id: str) -> bool:
        query = (
            sa.select(workflow_executions.c.id)
            .where(workflow_executions.c.id == execution_id)
        )
        return (await conn.execute(query)).fetchone() is not None

    async def list_executions(self, workflow_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent executions for a workflow, newest first."""
        query = (
            sa.select(workflow_executions)
            .where(workflow_executions.c.workflow_id == workflow_id)
            .order_by(workflow_executions.c.created_at.desc())
            .limit(limit)
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return [self._row_to_dict(row) for row in rows]

    async def list_recent(
        self, limit: int = 5, include_tests: bool = False
    ) -> list[dict[str, Any]]:
        """Return recent executions across all workflows, newest first.

        BUG-041: test-run executions are excluded from production aggregates
        by default so 'last execution status' reflects real runs.
        """
        query = sa.select(workflow_executions)
        if not include_tests:
            query = query.where(workflow_executions.c.is_test == 0)
        query = query.order_by(workflow_executions.c.created_at.desc()).limit(limit)
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return [self._row_to_dict(row) for row in rows]

    async def get_last_execution_per_workflow(
        self, workflow_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Return the most recent execution for each workflow in the given list."""
        if not workflow_ids:
            return {}
        # Use a window function or subquery to get the latest per workflow
        # For SQLite compatibility, use a correlated subquery approach
        subquery = (
            sa.select(
                workflow_executions.c.workflow_id,
                sa.func.max(workflow_executions.c.created_at).label("max_created_at"),
            )
            .where(
                (workflow_executions.c.workflow_id.in_(workflow_ids))
                & (workflow_executions.c.is_test == 0)
            )
            .group_by(workflow_executions.c.workflow_id)
            .subquery()
        )
        query = sa.select(workflow_executions).join(
            subquery,
            (workflow_executions.c.workflow_id == subquery.c.workflow_id)
            & (workflow_executions.c.created_at == subquery.c.max_created_at),
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return {row.workflow_id: self._row_to_dict(row) for row in rows}

    async def get_execution(self, execution_id: str) -> dict[str, Any] | None:
        """Return a single execution by ID, or None if not found."""
        query = sa.select(workflow_executions).where(workflow_executions.c.id == execution_id)
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            row = result.fetchone()
            if row is None:
                return None
            return self._row_to_dict(row)

    async def list_failed(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent executions with error status, newest first."""
        query = (
            sa.select(workflow_executions)
            .where(workflow_executions.c.status.in_(["error", "failed"]))
            .order_by(workflow_executions.c.created_at.desc())
            .limit(limit)
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return [self._row_to_dict(row) for row in rows]

    def _row_to_dict(self, row: Any) -> dict[str, Any]:
        """Convert a database row to a plain dict."""
        return {
            "id": row.id,
            "workflow_id": row.workflow_id,
            "version": row.version,
            "status": row.status,
            "trigger_payload": json.loads(row.trigger_payload) if row.trigger_payload else {},
            "node_results": json.loads(row.node_results) if row.node_results else [],
            "total_elapsed_ms": row.total_elapsed_ms,
            "total_prompt_tokens": row.total_prompt_tokens,
            "total_completion_tokens": row.total_completion_tokens,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
