"""Scheduler tools — let the model create and manage scheduled tasks."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from hestia.core.types import Session
from hestia.persistence.scheduler import SchedulerStore
from hestia.persistence.sessions import SessionStore
from hestia.runtime_context import current_platform, current_platform_user
from hestia.tools.capabilities import ORCHESTRATION
from hestia.tools.metadata import tool


async def _get_session_for_tool(
    session_store: SessionStore, description: str
) -> Session | str:
    platform = current_platform.get()
    platform_user = current_platform_user.get()

    if platform is None or platform_user is None:
        return (
            f"Error: Cannot {description} outside a platform context. "
            "Run this from Telegram or Matrix."
        )

    return await session_store.get_or_create_session(platform, platform_user)


async def _verify_task_ownership(
    scheduler_store: SchedulerStore, task_id: str, session_id: str
) -> str | None:
    task = await scheduler_store.get_task(task_id)
    if task is None:
        return f"Error: Task {task_id} not found."
    if task.session_id != session_id:
        return "Error: Task does not belong to your session."
    return None


def make_create_scheduled_task_tool(
    scheduler_store: SchedulerStore,
    session_store: SessionStore,
) -> Callable[..., Coroutine[Any, Any, str]]:
    """Create a tool that lets the model schedule recurring tasks."""

    @tool(
        name="create_scheduled_task",
        public_description="Create a recurring scheduled task. Params: prompt (str), cron_expression (str), description (str, default ''), notify (bool, default False).",

        tags=["scheduler", "builtin"],
        capabilities=[ORCHESTRATION],
    )
    async def create_scheduled_task(
        prompt: str,
        cron_expression: str,
        description: str = "",
        notify: bool = False,
    ) -> str:
        """Create a scheduled task that runs on a cron schedule.

        The task will execute the given prompt automatically at each scheduled
        time. Use this when the user asks for recurring jobs, cron jobs, or
        automated tasks.

        Args:
            prompt: The instruction to execute on each run (e.g., "Check the
                weather and summarize any new posts")
            cron_expression: Cron expression for the schedule. Examples:
                - "0 9 * * *" → daily at 9:00 AM
                - "*/30 6-8 * * *" → every 30 min from 6:00-8:30 AM
                - "0 */1 * * *" → every hour
            description: Optional human-readable description of the task
            notify: If True, push the task output to the user's platform
                (Telegram/Matrix) on each run

        Returns:
            Confirmation with the task ID and next run time.
        """
        session = await _get_session_for_tool(session_store, "create scheduled task")
        if isinstance(session, str):
            return session

        task = await scheduler_store.create_task(
            session_id=session.id,
            prompt=prompt,
            description=description or prompt[:80],
            cron_expression=cron_expression,
            notify=notify,
        )

        next_run_str = task.next_run_at.strftime("%Y-%m-%d %H:%M") if task.next_run_at else "N/A"
        return (
            f"Created scheduled task {task.id}\n"
            f"  Schedule: cron '{cron_expression}'\n"
            f"  Next run: {next_run_str}\n"
            f"  Notify: {'yes' if notify else 'no'}"
        )

    return create_scheduled_task


def make_list_scheduled_tasks_tool(
    scheduler_store: SchedulerStore,
    session_store: SessionStore,
) -> Callable[..., Coroutine[Any, Any, str]]:
    """Create a tool that lists scheduled tasks."""

    @tool(
        name="list_scheduled_tasks",
        public_description="List scheduled tasks for the current user. Params: include_disabled (bool, default False).",
        tags=["scheduler", "builtin"],
        capabilities=[ORCHESTRATION],
    )
    async def list_scheduled_tasks(include_disabled: bool = False) -> str:
        """List scheduled tasks for the current user.

        Args:
            include_disabled: If True, also show disabled tasks

        Returns:
            Formatted list of tasks with IDs, schedules, and status.
        """
        session = await _get_session_for_tool(session_store, "list scheduled tasks")
        if isinstance(session, str):
            return session

        tasks = await scheduler_store.list_tasks_for_session(
            session_id=session.id, include_disabled=include_disabled
        )

        if not tasks:
            return "No scheduled tasks found."

        lines = []
        for t in tasks:
            status = "enabled" if t.enabled else "disabled"
            next_run = t.next_run_at.strftime("%Y-%m-%d %H:%M") if t.next_run_at else "N/A"
            desc = t.description or "(no description)"
            lines.append(
                f"- {t.id}: {desc}\n"
                f"  status: {status} | cron: {t.cron_expression} | next: {next_run}"
            )
        return "\n".join(lines)

    return list_scheduled_tasks


def make_disable_scheduled_task_tool(
    scheduler_store: SchedulerStore,
    session_store: SessionStore,
) -> Callable[..., Coroutine[Any, Any, str]]:
    """Create a tool that disables a scheduled task."""

    @tool(
        name="disable_scheduled_task",
        public_description="Disable a scheduled task by ID. Params: task_id (str).",
        tags=["scheduler", "builtin"],
        capabilities=[ORCHESTRATION],
        requires_confirmation=True,
    )
    async def disable_scheduled_task(task_id: str) -> str:
        """Disable a scheduled task so it stops running.

        Args:
            task_id: The ID of the task to disable

        Returns:
            Confirmation or error message.
        """
        session = await _get_session_for_tool(session_store, "disable scheduled task")
        if isinstance(session, str):
            return session

        error = await _verify_task_ownership(scheduler_store, task_id, session.id)
        if error:
            return error

        success = await scheduler_store.disable_task(task_id)
        if success:
            return f"Disabled scheduled task {task_id}."
        return f"Error: Could not disable task {task_id}."

    return disable_scheduled_task


def make_enable_scheduled_task_tool(
    scheduler_store: SchedulerStore,
    session_store: SessionStore,
) -> Callable[..., Coroutine[Any, Any, str]]:
    """Create a tool that re-enables a scheduled task."""

    @tool(
        name="enable_scheduled_task",
        public_description="Re-enable a disabled scheduled task by ID. Params: task_id (str).",
        tags=["scheduler", "builtin"],
        capabilities=[ORCHESTRATION],
    )
    async def enable_scheduled_task(task_id: str) -> str:
        """Re-enable a previously disabled scheduled task.

        Args:
            task_id: The ID of the task to enable

        Returns:
            Confirmation or error message.
        """
        session = await _get_session_for_tool(session_store, "enable scheduled task")
        if isinstance(session, str):
            return session

        error = await _verify_task_ownership(scheduler_store, task_id, session.id)
        if error:
            return error

        success = await scheduler_store.set_enabled(task_id, True)
        if success:
            return f"Enabled scheduled task {task_id}."
        return f"Error: Could not enable task {task_id}."

    return enable_scheduled_task


def make_delete_scheduled_task_tool(
    scheduler_store: SchedulerStore,
    session_store: SessionStore,
) -> Callable[..., Coroutine[Any, Any, str]]:
    """Create a tool that permanently deletes a scheduled task."""

    @tool(
        name="delete_scheduled_task",
        public_description="Permanently delete a scheduled task by ID. Params: task_id (str).",
        tags=["scheduler", "builtin"],
        capabilities=[ORCHESTRATION],
        requires_confirmation=True,
    )
    async def delete_scheduled_task(task_id: str) -> str:
        """Permanently delete a scheduled task.

        Args:
            task_id: The ID of the task to delete

        Returns:
            Confirmation or error message.
        """
        session = await _get_session_for_tool(session_store, "delete scheduled task")
        if isinstance(session, str):
            return session

        error = await _verify_task_ownership(scheduler_store, task_id, session.id)
        if error:
            return error

        success = await scheduler_store.delete_task(task_id)
        if success:
            return f"Deleted scheduled task {task_id}."
        return f"Error: Could not delete task {task_id}."

    return delete_scheduled_task
