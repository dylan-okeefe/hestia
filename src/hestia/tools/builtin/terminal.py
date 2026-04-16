"""Terminal/shell command tool."""

import asyncio
import os
import signal

from hestia.tools.capabilities import SHELL_EXEC
from hestia.tools.metadata import tool


@tool(
    name="terminal",
    public_description=(
        "Run a shell command and return stdout, stderr, and exit code. Use with caution."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "timeout": {
                "type": "number",
                "description": "Max seconds (default 30)",
            },
        },
        "required": ["command"],
    },
    max_inline_chars=4000,
    requires_confirmation=True,
    tags=["system"],
    capabilities=[SHELL_EXEC],
)
async def terminal(command: str, timeout: float = 30.0) -> str:
    """Run a shell command and return the result."""
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (PermissionError, ProcessLookupError, OSError):
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        await proc.wait()
        return f"TIMEOUT after {timeout}s"

    stdout_str = stdout.decode("utf-8", errors="replace")
    stderr_str = stderr.decode("utf-8", errors="replace")

    return (
        f"exit_code: {proc.returncode}\n--- stdout ---\n{stdout_str}\n--- stderr ---\n{stderr_str}"
    )
