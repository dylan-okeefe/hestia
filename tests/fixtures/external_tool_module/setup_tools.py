"""External tool module that uses ``setup(context)`` to create a store."""

from __future__ import annotations

from hestia.tools.capabilities import SHELL_EXEC
from hestia.tools.external_context import ExternalToolModuleContext
from hestia.tools.metadata import tool
from hestia.tools.registry import ToolRegistry

store: dict[str, str] = {}
module_context: ExternalToolModuleContext | None = None


@tool(
    name="external_store_read",
    public_description="Read a value from the module store.",
    parameters_schema={
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "Key to read"},
        },
        "required": ["key"],
    },
)
async def external_store_read(key: str) -> str:
    """Return the value stored for ``key`` during setup."""
    return store.get(key, "")


@tool(
    name="external_store_shell",
    public_description="Run a shell command (external setup tool).",
    parameters_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to run"},
        },
        "required": ["command"],
    },
    capabilities=[SHELL_EXEC],
)
async def external_store_shell(command: str) -> str:
    """Pretend to run a shell command."""
    return f"would run: {command}"


def setup(context: ExternalToolModuleContext) -> None:
    """Create the module store and remember the context."""
    global module_context, store
    module_context = context
    store.clear()
    store["greeting"] = "hello from setup"


def register(registry: ToolRegistry) -> None:
    """Register this module's tools with Hestia."""
    registry.register(external_store_read)
    registry.register(external_store_shell)
