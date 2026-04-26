"""Terminal/shell command tool."""

import asyncio
import logging
import os
import re
import signal
from typing import Any

from hestia.tools.capabilities import SHELL_EXEC
from hestia.tools.metadata import tool

logger = logging.getLogger(__name__)

# Default patterns that are blocked regardless of config. These are
# defense-in-depth rails, not a security boundary — the trust system
# and confirmation callback remain the primary controls.
_DEFAULT_BLOCKED_PATTERNS = [
    r">\s*/dev/[sh]d[a-z]",  # redirect to block device
    r"dd\s+if=.*of=/dev/[sh]d",  # disk overwrite
    r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:&\s*\};\s*:",  # fork bomb
    r"rm\s+-[rf].*/\s*(;|$|\|)",  # rm -rf /
    r"mkfs\.[a-z0-9]+\s+/dev/[sh]d",  # filesystem creation on raw disk
]


def make_terminal_tool(blocked_patterns: list[str] | None = None) -> Any:
    """Create a terminal tool with optional command-blocking patterns.

    Args:
        blocked_patterns: Regex patterns that, if matched anywhere in the
            command string, cause the tool to return an error without execution.
            Defaults to a small set of catastrophically dangerous patterns.
    """
    patterns = [_re_compile(p) for p in (blocked_patterns or _DEFAULT_BLOCKED_PATTERNS)]

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
        for pat in patterns:
            if pat.search(command):
                logger.warning("Blocked terminal command matching pattern %r: %s", pat.pattern, command)
                return f"BLOCKED: Command matches a prohibited pattern ({pat.pattern})."

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

    return terminal


def _re_compile(pattern: str) -> re.Pattern[str]:
    """Compile a regex pattern, raising a clear error on invalid syntax."""
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise ValueError(f"Invalid blocked_shell_pattern regex: {pattern!r} — {exc}") from exc
