"""Scheduler tools — let the model create and manage scheduled tasks."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any, cast

from hestia.persistence.scheduler import SchedulerStore
from hestia.persistence.sessions import SessionStore
from hestia.runtime_context import current_platform, current_platform_user
from hestia.tools.capabilities import ORCHESTRATION
from hestia.tools.metadata import tool


def make_create_scheduled_task_tool(
    scheduler_store: SchedulerStore,
    session_store: SessionStore,
) -> Callable[..., Coroutine[Any, Any, str]]:
    """Create a tool that lets the model schedule recurring tasks."""

    @tool(
        name="create_scheduled_task",
        public_description="Create a recurring scheduled task that runs automatically.",
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
        platform = current_platform.get()
        platform_user = current_platform_user.get()

        if platform is None or platform_user is None:
            return (
                "Error: Cannot create scheduled task outside a platform context. "
                "Run this from Telegram or Matrix."
            )

        session = await session_store.get_or_create_session(platform, platform_user)

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

    return cast("Callable[..., Coroutine[Any, Any, str]]", create_scheduled_task)
