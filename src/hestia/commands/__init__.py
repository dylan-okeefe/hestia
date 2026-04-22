"""CLI command implementations for Hestia.

Split by domain into submodules; this package re-exports the public
_cmd_* entry points so that ``from hestia.commands import ...`` continues
to work unchanged.
"""

from __future__ import annotations

from typing import Any

from hestia.commands.admin import (
    _cmd_audit_egress,
    _cmd_audit_run,
    _cmd_doctor,
    _cmd_email_check,
    _cmd_email_list_cmd,
    _cmd_email_read_cmd,
    _cmd_failures_list,
    _cmd_failures_summary,
    _cmd_health,
    _cmd_init,
    _cmd_status,
)
from hestia.commands.chat import _cmd_ask, _cmd_chat
from hestia.commands.policy import _cmd_policy_show
from hestia.commands.reflection import (
    _cmd_reflection_accept,
    _cmd_reflection_defer,
    _cmd_reflection_history,
    _cmd_reflection_list,
    _cmd_reflection_reject,
    _cmd_reflection_run,
    _cmd_reflection_show,
    _cmd_reflection_status,
)
from hestia.commands.scheduler import (
    _cmd_schedule_add,
    _cmd_schedule_daemon,
    _cmd_schedule_disable,
    _cmd_schedule_enable,
    _cmd_schedule_list,
    _cmd_schedule_remove,
    _cmd_schedule_run,
    _cmd_schedule_show,
)
from hestia.commands.style import _cmd_style_show
from hestia.commands.tools import (
    _cmd_skill_demote,
    _cmd_skill_disable,
    _cmd_skill_list,
    _cmd_skill_promote,
    _cmd_skill_show,
)

__all__ = [
    "cli",
    "_cmd_ask",
    "_cmd_audit_egress",
    "_cmd_audit_run",
    "_cmd_chat",
    "_cmd_doctor",
    "_cmd_email_check",
    "_cmd_email_list_cmd",
    "_cmd_email_read_cmd",
    "_cmd_failures_list",
    "_cmd_failures_summary",
    "_cmd_health",
    "_cmd_init",
    "_cmd_policy_show",
    "_cmd_reflection_accept",
    "_cmd_reflection_defer",
    "_cmd_reflection_history",
    "_cmd_reflection_list",
    "_cmd_reflection_reject",
    "_cmd_reflection_run",
    "_cmd_reflection_show",
    "_cmd_reflection_status",
    "_cmd_schedule_add",
    "_cmd_schedule_daemon",
    "_cmd_schedule_disable",
    "_cmd_schedule_enable",
    "_cmd_schedule_list",
    "_cmd_schedule_remove",
    "_cmd_schedule_run",
    "_cmd_schedule_show",
    "_cmd_skill_demote",
    "_cmd_skill_disable",
    "_cmd_skill_list",
    "_cmd_skill_promote",
    "_cmd_skill_show",
    "_cmd_status",
    "_cmd_style_show",
]


def __getattr__(name: str) -> Any:
    """Lazy re-export of ``cli`` to avoid circular imports with ``hestia.cli``."""
    if name == "cli":
        from hestia.cli import cli as _cli

        return _cli
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
