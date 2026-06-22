"""Scheduler wiring for memory maintenance tasks."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from hestia.core.types import ScheduledTask
from hestia.persistence.scheduler import SchedulerStore

if TYPE_CHECKING:
    from hestia.config import MemoryMaintenanceConfig


_TASK_TYPE_DETERMINISTIC = "memory_maintenance_deterministic"
_TASK_TYPE_LLM = "memory_maintenance_llm"


def _task_prompt(platform: str, platform_user: str) -> str:
    """Encode the target identity in the task prompt."""
    return json.dumps({"platform": platform, "platform_user": platform_user})


def _parse_task_prompt(prompt: str) -> tuple[str, str]:
    """Decode the target identity from a task prompt."""
    try:
        data = json.loads(prompt)
        return str(data["platform"]), str(data["platform_user"])
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"Invalid memory maintenance task prompt: {prompt!r}") from exc


async def ensure_memory_maintenance_tasks(
    scheduler_store: SchedulerStore,
    session_id: str,
    config: MemoryMaintenanceConfig,
    platform: str,
    platform_user: str,
) -> tuple[ScheduledTask, ScheduledTask]:
    """Create or update the deterministic and LLM maintenance tasks.

    Calling this twice for the same identity updates the existing tasks
    instead of duplicating them.
    """
    prompt = _task_prompt(platform, platform_user)
    description = f"Memory maintenance for {platform}/{platform_user}"

    existing = await scheduler_store.list_tasks_for_session(session_id)

    deterministic_task: ScheduledTask | None = None
    llm_task: ScheduledTask | None = None
    for task in existing:
        if task.task_type == _TASK_TYPE_DETERMINISTIC:
            deterministic_task = await scheduler_store.update_task(
                task.id,
                prompt=prompt,
                description=description,
                cron_expression=config.deterministic_cron,
                enabled=True,
            )
        elif task.task_type == _TASK_TYPE_LLM:
            llm_task = await scheduler_store.update_task(
                task.id,
                prompt=prompt,
                description=description,
                cron_expression=config.llm_cron,
                enabled=True,
            )

    if deterministic_task is None:
        deterministic_task = await scheduler_store.create_task(
            session_id=session_id,
            prompt=prompt,
            description=description,
            cron_expression=config.deterministic_cron,
            notify=True,
            task_type=_TASK_TYPE_DETERMINISTIC,
        )

    if llm_task is None:
        llm_task = await scheduler_store.create_task(
            session_id=session_id,
            prompt=prompt,
            description=description,
            cron_expression=config.llm_cron,
            notify=True,
            task_type=_TASK_TYPE_LLM,
        )

    return deterministic_task, llm_task


__all__ = [
    "ensure_memory_maintenance_tasks",
    "_parse_task_prompt",
    "_TASK_TYPE_DETERMINISTIC",
    "_TASK_TYPE_LLM",
]
