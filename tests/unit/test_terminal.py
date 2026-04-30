"""Unit tests for terminal tool."""

import asyncio
import contextlib
import os
import tempfile

import pytest

from hestia.tools.builtin.terminal import make_terminal_tool

terminal = make_terminal_tool()


class TestTerminal:
    """Tests for terminal tool."""

    @pytest.mark.asyncio
    async def test_terminal_runs_command(self):
        """Terminal runs a simple command and returns output."""
        result = await terminal("echo hello", timeout=5.0)
        assert "exit_code: 0" in result
        assert "hello" in result

    @pytest.mark.asyncio
    async def test_timeout_kills_process_group(self):
        """Timeout kills the entire process group including children."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            # Write a script that records its own PID and the PID of a background sleep
            f.write("#!/bin/bash\n")
            f.write("echo $$ > /tmp/terminal_test_parent_pid\n")
            f.write("sleep 60 &\n")
            f.write("echo $! > /tmp/terminal_test_child_pid\n")
            f.write("wait\n")
            script_path = f.name

        try:
            result = await terminal(f"bash {script_path}", timeout=0.5)
            assert "TIMEOUT after 0.5s" in result

            # Give the OS a moment to reap processes
            await asyncio.sleep(0.3)

            parent_pid_file = "/tmp/terminal_test_parent_pid"
            child_pid_file = "/tmp/terminal_test_child_pid"

            if os.path.exists(parent_pid_file) and os.path.exists(child_pid_file):
                with open(parent_pid_file) as f:
                    parent_pid = int(f.read().strip())
                with open(child_pid_file) as f:
                    child_pid = int(f.read().strip())

                # Both parent and child should be dead
                assert not _is_process_alive(parent_pid), f"Parent process {parent_pid} still alive"
                assert not _is_process_alive(child_pid), f"Child process {child_pid} still alive"
        finally:
            paths = (script_path, "/tmp/terminal_test_parent_pid", "/tmp/terminal_test_child_pid")
            for path in paths:
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(path)

    @pytest.mark.asyncio
    async def test_timeout_returns_timeout_message(self):
        """Timeout returns the TIMEOUT message."""
        result = await terminal("sleep 10", timeout=0.2)
        assert "TIMEOUT after 0.2s" in result


def _is_process_alive(pid: int) -> bool:
    """Check if a process is still alive."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, OSError):
        return False
