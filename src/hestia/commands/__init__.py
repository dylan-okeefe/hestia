"""CLI command implementations for Hestia.

Split by domain into submodules; this package re-exports the public
cmd_* entry points so that ``from hestia.commands import ...`` continues
to work unchanged.
"""

from __future__ import annotations

from typing import Any

from hestia.commands.admin import (
    cmd_artifacts_list,
    cmd_artifacts_purge,
    cmd_audit_egress,
    cmd_audit_run,
    cmd_doctor,
    cmd_email_check,
    cmd_email_list_cmd,
    cmd_email_read_cmd,
    cmd_failures_list,
    cmd_failures_summary,
    cmd_health,
    cmd_init,
    cmd_status,
)
from hestia.commands.chat import cmd_ask, cmd_chat
from hestia.commands.history import cmd_history_list, cmd_history_show
from hestia.commands.policy import cmd_policy_show
from hestia.commands.reflection import (
    cmd_reflection_accept,
    cmd_reflection_defer,
    cmd_reflection_history,
    cmd_reflection_list,
    cmd_reflection_reject,
    cmd_reflection_run,
    cmd_reflection_show,
    cmd_reflection_status,
)
from hestia.commands.scheduler import (
    cmd_schedule_add,
    cmd_schedule_daemon,
    cmd_schedule_disable,
    cmd_schedule_enable,
    cmd_schedule_list,
    cmd_schedule_remove,
    cmd_schedule_run,
    cmd_schedule_show,
)
from hestia.commands.style import cmd_style_show
__all__ = [
    "cli",
    "cmd_ask",
    "cmd_audit_egress",
    "cmd_audit_run",
    "cmd_chat",
    "cmd_doctor",
    "cmd_email_check",
    "cmd_email_list_cmd",
    "cmd_email_read_cmd",
    "cmd_failures_list",
    "cmd_failures_summary",
    "cmd_health",
    "cmd_history_list",
    "cmd_history_show",
    "cmd_artifacts_list",
    "cmd_artifacts_purge",
    "cmd_init",
    "cmd_policy_show",
    "cmd_reflection_accept",
    "cmd_reflection_defer",
    "cmd_reflection_history",
    "cmd_reflection_list",
    "cmd_reflection_reject",
    "cmd_reflection_run",
    "cmd_reflection_show",
    "cmd_reflection_status",
    "cmd_schedule_add",
    "cmd_schedule_daemon",
    "cmd_schedule_disable",
    "cmd_schedule_enable",
    "cmd_schedule_list",
    "cmd_schedule_remove",
    "cmd_schedule_run",
    "cmd_schedule_show",
    "cmd_status",
    "cmd_style_show",
]


def __getattr__(name: str) -> Any:
    """Lazy re-export of ``cli`` to avoid circular imports with ``hestia.cli``."""
    if name == "cli":
        from hestia.cli import cli as _cli

        return _cli
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
