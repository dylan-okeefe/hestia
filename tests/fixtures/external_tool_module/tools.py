"""Example external tool module for Hestia tests."""

from __future__ import annotations

from hestia.tools.capabilities import SHELL_EXEC
from hestia.tools.metadata import tool
from hestia.tools.registry import ToolRegistry


@tool(
    name="external_echo",
    public_description="Echo the provided message back.",
    parameters_schema={
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Message to echo"},
        },
        "required": ["message"],
    },
)
async def external_echo(message: str) -> str:
    """Echo the provided message back."""
    return message


@tool(
    name="external_shell",
    public_description="Run a shell command (external tool).",
    parameters_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to run"},
        },
        "required": ["command"],
    },
    capabilities=[SHELL_EXEC],
)
async def external_shell(command: str) -> str:
    """Run a shell command (external tool)."""
    return f"would run: {command}"


def register(registry: ToolRegistry) -> None:
    """Register this module's tools with Hestia."""
    registry.register(external_echo)
    registry.register(external_shell)
