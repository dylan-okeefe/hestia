"""Terminal/shell command tool."""

import asyncio
import contextlib
import logging
import os
import re
import signal
from typing import Any

from hestia.tools.capabilities import SHELL_EXEC
from hestia.tools.metadata import tool

logger = logging.getLogger(__name__)

# Default patterns that are blocked regardless of config. These are weak
# defense-in-depth heuristics, not a security boundary — a determined actor
# can bypass them with trivial obfuscation (e.g. `r\m`, variable expansion,
# or targeting `/etc` instead of `/`). The trust system and confirmation
# callback remain the primary controls.
_DEFAULT_BLOCKED_PATTERNS = [
    r">\s*/dev/[sh]d[a-z]",  # redirect to block device
    r"dd\s+if=.*of=/dev/[sh]d",  # disk overwrite
    r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:&\s*\};\s*:",  # fork bomb
    r"rm\s+-[rf].*/\*?\s*(;|$|\|)",  # rm -rf / or rm -rf /*
    r"mkfs\.[a-z0-9]+\s+/dev/[sh]d",  # filesystem creation on raw disk
]


_TERMINAL_MAX_TIMEOUT_S = 600.0
_TERMINAL_MAX_OUTPUT_BYTES = 1_000_000

# Environment allowlist for child processes (SEC-015): the model could
# previously run `printenv` and pull every host secret into context.
_TERMINAL_ENV_ALLOWLIST = (
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "TERM", "TMPDIR",
    "LANG", "LANGUAGE",
)


def make_terminal_tool(blocked_patterns: list[str] | None = None) -> Any:
    """Create a terminal tool with optional command-blocking patterns.

    Args:
        blocked_patterns: Regex patterns that, if matched anywhere in the
            command string, cause the tool to return an error without execution.
            Defaults to a small set of catastrophically dangerous patterns.
            These are weak heuristics, not a security boundary.
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
                "description": {
                    "type": "string",
                    "description": "Optional human-readable description of what the command does. Ignored.",
                },
            },
            "required": ["command"],
        },
        max_inline_chars=4000,
        requires_confirmation=True,
        tags=["system"],
        capabilities=[SHELL_EXEC],
    )
    async def terminal(command: str, timeout: float = 30.0, description: str = "") -> str:
        """Run a shell command and return the result."""
        # Clamp model-controlled timeouts; 'timeout=100000' used to hang turns.
        effective_timeout = min(float(timeout), _TERMINAL_MAX_TIMEOUT_S)

        env = {
            k: v for k, v in os.environ.items() if k in _TERMINAL_ENV_ALLOWLIST
        }

        for pat in patterns:
            if pat.search(command):
                logger.warning("Blocked terminal command matching pattern %r: %s", pat.pattern, command)
                return f"BLOCKED: Command matches a prohibited pattern ({pat.pattern})."

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            env=env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=effective_timeout)
        except TimeoutError:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (PermissionError, ProcessLookupError, OSError):
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
            await proc.wait()
            return f"TIMEOUT after {effective_timeout}s"

        # Cap captured output so `cat /dev/urandom | base64` cannot buffer
        # gigabytes in RAM before truncation happens downstream.
        def _bounded(raw: bytes) -> tuple[str, bool]:
            data = raw[:_TERMINAL_MAX_OUTPUT_BYTES]
            truncated = len(raw) > _TERMINAL_MAX_OUTPUT_BYTES
            return data.decode("utf-8", errors="replace"), truncated

        stdout_str, stdout_trunc = _bounded(stdout)
        stderr_str, stderr_trunc = _bounded(stderr)
        if stdout_trunc:
            stdout_str += "\n[output truncated]"
        if stderr_trunc:
            stderr_str += "\n[stderr truncated]"

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
