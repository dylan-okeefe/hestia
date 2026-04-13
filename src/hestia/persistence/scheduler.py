"""Scheduler persistence layer for scheduled tasks."""

import uuid
from datetime import datetime, timezone, tzinfo
from typing import Any

import sqlalchemy as sa
from croniter import croniter

from hestia.core.types import ScheduledTask
from hestia.errors import PersistenceError
from hestia.persistence.db import Database
from hestia.persistence.schema import scheduled_tasks


def _generate_task_id() -> str:
    """Generate a unique task ID."""
    return f"task_{uuid.uuid4().hex[:16]}"


def _dt_gt_utc(left: datetime, right: datetime) -> bool:
    """True if *left* is after *right* on the UTC timeline (naive datetimes treated as UTC)."""

    def as_utc_aware(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    return as_utc_aware(left) > as_utc_aware(right)


def _calculate_next_run(
    cron_expr: str | None,
    fire_at: datetime | None,
    base_time: datetime | None = None,
    created_at: datetime | None = None,
) -> datetime | None:
    """Calculate the next run time from a cron expression or fire_at time.

    Args:
        cron_expr: Cron expression for recurring tasks (e.g., "0 9 * * *")
        fire_at: Exact datetime for one-time tasks
        base_time: Base time for cron calculation (defaults to now in local timezone)
        created_at: Task creation time (used when fire_at is in the past)

    Returns:
        The next scheduled run time, or None if the task should not run again.
    """
    if fire_at is not None:
        # One-time task - run at fire_at, or immediately if fire_at is in the past
        if base_time is None:
            base_time = datetime.now(timezone.utc)
        # Normalize both to UTC for comparison
        fire_at_utc = fire_at if fire_at.tzinfo else fire_at.replace(tzinfo=timezone.utc)
        base_time_utc = base_time if base_time.tzinfo else base_time.replace(tzinfo=timezone.utc)
        if fire_at_utc > base_time_utc:
            return fire_at
        # fire_at is in the past, run immediately (use created_at if provided)
        return created_at if created_at else base_time

    if cron_expr is not None:
        # Recurring task - calculate next occurrence from cron expression
        if base_time is None:
            base_time = datetime.now(timezone.utc)
        try:
            itr = croniter(cron_expr, base_time)
            return itr.get_next(datetime)
        except (ValueError, TypeError) as e:
            raise PersistenceError(f"Invalid cron expression '{cron_expr}': {e}") from e

    return None


class SchedulerStore:
    """Typed CRUD wrapper for scheduled task persistence."""

    def __init__(self, db: Database) -> None:
        """Initialize with a Database instance."""
        self._db = db

    async def create_task(
        self,
        session_id: str,
        prompt: str,
        description: str | None = None,
        cron_expression: str | None = None,
        fire_at: datetime | None = None,
        enabled: bool = True,
    ) -> ScheduledTask:
        """Create a new scheduled task.

        Args:
            session_id: Session ID to run the task in
            prompt: The prompt text to send to the model
            description: Optional human-readable description
            cron_expression: Cron expression for recurring tasks (e.g., "0 9 * * *")
            fire_at: Exact datetime for one-time tasks
            enabled: Whether the task is initially enabled

        Returns:
            The created ScheduledTask

        Raises:
            PersistenceError: If neither cron_expression nor fire_at is provided,
                or if both are provided.
        """
        # Validate that exactly one scheduling method is provided
        if cron_expression is not None and fire_at is not None:
            raise PersistenceError("Cannot specify both cron_expression and fire_at")
        if cron_expression is None and fire_at is None:
            raise PersistenceError("Must specify either cron_expression or fire_at")

        task_id = _generate_task_id()
        created_at = datetime.now(timezone.utc)

        # Calculate initial next_run_at
        next_run_at = _calculate_next_run(cron_expression, fire_at, created_at, created_at)

        insert = sa.insert(scheduled_tasks).values(
            id=task_id,
            session_id=session_id,
            prompt=prompt,
            description=description,
            cron_expression=cron_expression,
            fire_at=fire_at,
            enabled=enabled,
            created_at=created_at,
            last_run_at=None,
            next_run_at=next_run_at,
            last_error=None,
        )

        async with self._db.engine.connect() as conn:
            await conn.execute(insert)
            await conn.commit()

        return ScheduledTask(
            id=task_id,
            session_id=session_id,
            prompt=prompt,
            description=description,
            cron_expression=cron_expression,
            fire_at=fire_at,
            enabled=enabled,
            created_at=created_at,
            last_run_at=None,
            next_run_at=next_run_at,
            last_error=None,
        )

    async def list_due_tasks(
        self, now: datetime | None = None, limit: int = 100
    ) -> list[ScheduledTask]:
        """List tasks that are due to run.

        Args:
            now: Current time (defaults to now in local timezone)
            limit: Maximum number of tasks to return

        Returns:
            List of tasks where next_run_at <= now and enabled=True
        """
        if now is None:
            now = datetime.now(timezone.utc)

        query = (
            sa.select(scheduled_tasks)
            .where(
                sa.and_(
                    scheduled_tasks.c.enabled == True,
                    scheduled_tasks.c.next_run_at <= now,
                )
            )
            .order_by(scheduled_tasks.c.next_run_at)
            .limit(limit)
        )

        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return [self._row_to_task(row) for row in rows]

    async def list_tasks_for_session(
        self, session_id: str | None = None, include_disabled: bool = False
    ) -> list[ScheduledTask]:
        """List all tasks for a session, or all tasks if no session specified.

        Args:
            session_id: The session ID to filter by, or None for all tasks
            include_disabled: Whether to include disabled tasks

        Returns:
            List of tasks for the session
        """
        conditions: list = []
        if session_id is not None:
            conditions.append(scheduled_tasks.c.session_id == session_id)
        if not include_disabled:
            conditions.append(scheduled_tasks.c.enabled == True)

        query = sa.select(scheduled_tasks).order_by(scheduled_tasks.c.created_at.desc())
        if conditions:
            query = query.where(sa.and_(*conditions))

        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return [self._row_to_task(row) for row in rows]

    async def update_after_run(
        self,
        task_id: str,
        error: str | None = None,
        now: datetime | None = None,
        next_run_at: datetime | None = None,
    ) -> ScheduledTask | None:
        """Update a task after it has been executed.

        For recurring tasks (cron_expression), calculates the next run time.
        For one-time tasks (fire_at), disables the task.

        Args:
            task_id: The task ID
            error: Error message if the run failed, None if successful
            now: Current time (defaults to now in local timezone)

        Returns:
            The updated ScheduledTask, or None if not found
        """
        if now is None:
            now = datetime.now(timezone.utc)

        # First get the task to determine its type
        query = sa.select(scheduled_tasks).where(scheduled_tasks.c.id == task_id)

        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            row = result.fetchone()
            if not row:
                return None

            task = self._row_to_task(row)

            # Calculate next run time if not provided
            if next_run_at is None:
                if error is not None:
                    # Failed run - keep enabled for retry
                    next_run_at = task.next_run_at
                elif task.cron_expression is not None:
                    # Recurring task - calculate next occurrence
                    next_run_at = _calculate_next_run(task.cron_expression, None, now)
                else:
                    # One-time task - disable after successful run
                    next_run_at = None

            # Update the task
            values = {
                "last_run_at": now,
                "next_run_at": next_run_at,
                "last_error": error,
            }
            if task.cron_expression is None and error is None:
                # One-time task completed successfully - disable it
                values["enabled"] = False

            update = (
                sa.update(scheduled_tasks).where(scheduled_tasks.c.id == task_id).values(**values)
            )
            await conn.execute(update)
            await conn.commit()

            # Return updated task
            return ScheduledTask(
                id=task.id,
                session_id=task.session_id,
                prompt=task.prompt,
                description=task.description,
                cron_expression=task.cron_expression,
                fire_at=task.fire_at,
                enabled=values.get("enabled", task.enabled),
                created_at=task.created_at,
                last_run_at=now,
                next_run_at=next_run_at,
                last_error=error,
            )

    async def set_enabled(self, task_id: str, enabled: bool) -> bool:
        """Enable or disable a scheduled task.

        Returns True if the task was found, False otherwise.
        """
        update = (
            sa.update(scheduled_tasks)
            .where(scheduled_tasks.c.id == task_id)
            .values(enabled=enabled)
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(update)
            await conn.commit()
            return result.rowcount > 0

    async def disable_task(self, task_id: str) -> bool:
        """Disable a scheduled task.

        Args:
            task_id: The task ID to disable

        Returns:
            True if the task was found and disabled, False otherwise
        """
        return await self.set_enabled(task_id, False)

    async def delete_task(self, task_id: str) -> bool:
        """Permanently delete a scheduled task.

        Returns True if the task was found and deleted, False otherwise.
        """
        delete = sa.delete(scheduled_tasks).where(scheduled_tasks.c.id == task_id)
        async with self._db.engine.connect() as conn:
            result = await conn.execute(delete)
            await conn.commit()
            return result.rowcount > 0

    async def get_task(self, task_id: str) -> ScheduledTask | None:
        """Get a task by ID.

        Args:
            task_id: The task ID

        Returns:
            The ScheduledTask, or None if not found
        """
        query = sa.select(scheduled_tasks).where(scheduled_tasks.c.id == task_id)

        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            row = result.fetchone()
            if row:
                return self._row_to_task(row)
            return None

    def _row_to_task(self, row: Any) -> ScheduledTask:
        """Convert a database row to a ScheduledTask dataclass.

        Ensures datetime fields are UTC-aware (SQLite stores naive datetimes).
        """

        def _ensure_utc(dt: datetime | None) -> datetime | None:
            if dt is None:
                return None
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

        return ScheduledTask(
            id=row.id,
            session_id=row.session_id,
            prompt=row.prompt,
            description=row.description,
            cron_expression=row.cron_expression,
            fire_at=_ensure_utc(row.fire_at),
            enabled=row.enabled,
            created_at=_ensure_utc(row.created_at),
            last_run_at=_ensure_utc(row.last_run_at),
            next_run_at=_ensure_utc(row.next_run_at),
            last_error=row.last_error,
        )

    async def summary_stats(self) -> dict[str, Any]:
        """Get summary stats for the status command.

        Returns:
            Dict with:
                - enabled_count: Number of enabled tasks
                - next_run_at: Earliest next_run_at among enabled tasks, or None
        """
        count_query = sa.select(sa.func.count(scheduled_tasks.c.id)).where(
            scheduled_tasks.c.enabled.is_(True)
        )
        next_run_query = sa.select(sa.func.min(scheduled_tasks.c.next_run_at)).where(
            sa.and_(
                scheduled_tasks.c.enabled.is_(True),
                scheduled_tasks.c.next_run_at.is_not(None),
            )
        )

        async with self._db.engine.connect() as conn:
            count_result = await conn.execute(count_query)
            enabled_count = count_result.scalar_one() or 0

            next_run_result = await conn.execute(next_run_query)
            next_run_at = next_run_result.scalar_one()

            return {
                "enabled_count": enabled_count,
                "next_run_at": next_run_at,
            }
