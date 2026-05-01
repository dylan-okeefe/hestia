"""Built-in tools for Hestia.

Tool construction follows one of two patterns:

1. Plain @tool decorated function — for tools with no external dependencies
   (e.g. ``current_time``, ``http_get``, ``terminal``).

2. Factory function ``make_*_tool(...)`` returning a decorated function — for
   tools that need runtime dependencies bound at startup
   (e.g. ``make_read_file_tool(storage_config)``, ``make_search_memory_tool(memory_store)``).

When adding a new tool, prefer pattern (1) if the tool is self-contained.
Use pattern (2) only when the tool needs a config object, store, or adapter
that is not importable at module load time.
"""

from hestia.runtime_context import current_session_id, current_trace_store
from hestia.tools.builtin.current_time import current_time
from hestia.tools.builtin.delegate_task import SubagentResult, make_delegate_task_tool
from hestia.tools.builtin.email_tools import make_email_search_and_read_tool, make_email_tools
from hestia.tools.builtin.http_get import http_get, make_http_get_tool
from hestia.tools.builtin.list_dir import make_list_dir_tool
from hestia.tools.builtin.memory_tools import (
    make_delete_memory_tool,
    make_list_memories_tool,
    make_save_memory_tool,
    make_search_memory_tool,
)
from hestia.tools.builtin.proposal_tools import (
    make_accept_proposal_tool,
    make_defer_proposal_tool,
    make_list_proposals_tool,
    make_reject_proposal_tool,
    make_show_proposal_tool,
)
from hestia.tools.builtin.read_artifact import make_read_artifact_tool
from hestia.tools.builtin.read_file import make_read_file_tool
from hestia.tools.builtin.scheduler_tools import (
    make_create_scheduled_task_tool,
    make_delete_scheduled_task_tool,
    make_disable_scheduled_task_tool,
    make_enable_scheduled_task_tool,
    make_list_scheduled_tasks_tool,
)
from hestia.tools.builtin.search_web import search_web
from hestia.tools.builtin.style_tools import (
    make_reset_style_metric_tool,
    make_reset_style_profile_tool,
    make_show_style_profile_tool,
)
from hestia.tools.builtin.terminal import make_terminal_tool
from hestia.tools.builtin.web_search import make_web_search_tool
from hestia.tools.builtin.write_file import make_write_file_tool
from hestia.tools.capabilities import (
    EMAIL_SEND,
    MEMORY_READ,
    MEMORY_WRITE,
    NETWORK_EGRESS,
    ORCHESTRATION,
    READ_LOCAL,
    SELF_MANAGEMENT,
    SHELL_EXEC,
    WRITE_LOCAL,
)

__all__ = [
    "current_session_id",
    "current_trace_store",
    "current_time",
    "http_get",
    "make_http_get_tool",
    "make_list_dir_tool",
    "make_delegate_task_tool",
    "make_delete_memory_tool",
    "make_list_memories_tool",
    "make_create_scheduled_task_tool",
    "make_delete_scheduled_task_tool",
    "make_disable_scheduled_task_tool",
    "make_enable_scheduled_task_tool",
    "make_list_scheduled_tasks_tool",
    "make_read_artifact_tool",
    "make_read_file_tool",
    "make_save_memory_tool",
    "make_search_memory_tool",
    "search_web",
    "make_web_search_tool",
    "make_email_search_and_read_tool",
    "make_email_tools",
    "make_write_file_tool",
    "make_list_proposals_tool",
    "make_show_proposal_tool",
    "make_accept_proposal_tool",
    "make_reject_proposal_tool",
    "make_defer_proposal_tool",
    "make_show_style_profile_tool",
    "make_reset_style_metric_tool",
    "make_reset_style_profile_tool",
    "EMAIL_SEND",
    "MEMORY_READ",
    "MEMORY_WRITE",
    "NETWORK_EGRESS",
    "ORCHESTRATION",
    "READ_LOCAL",
    "SELF_MANAGEMENT",
    "SHELL_EXEC",
    "SubagentResult",
    "make_terminal_tool",
    "WRITE_LOCAL",
]
