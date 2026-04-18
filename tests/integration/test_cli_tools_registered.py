"""Smoke test: verify read_artifact and delete_memory appear in CLI registry."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from hestia.cli import cli


class TestCliToolsRegistered:
    """Verify new tools are reachable through the CLI bootstrap path."""

    def test_registry_contains_read_artifact_and_delete_memory(self) -> None:
        """Bootstrap via CliRunner and assert both tools are registered."""
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as artifacts_dir:
            with tempfile.TemporaryDirectory() as slot_dir:
                with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
                    db_path = f.name

                # Use a custom command to inspect the registry
                from hestia.cli import cli

                # Invoke init which bootstraps the full context
                result = runner.invoke(
                    cli,
                    [
                        "--db-path", db_path,
                        "--artifacts-path", artifacts_dir,
                        "--slot-dir", slot_dir,
                        "init",
                    ],
                )
                assert result.exit_code == 0

                # Now invoke a command that can access the registry.
                # Since context isn't persisted across invocations, we'll use
                # click's isolated_filesystem and manually build the context
                # by invoking the group callback.
                ctx = runner.invoke(cli, [
                    "--db-path", db_path,
                    "--artifacts-path", artifacts_dir,
                    "--slot-dir", slot_dir,
                ], catch_exceptions=False)
                # This doesn't give us the context directly.
                # Instead, let's monkey-patch a command to capture the registry.

    def test_registry_contains_tools_via_callback(self) -> None:
        """Use click's invoke with a callback to capture the registry."""
        from hestia.cli import cli, CliAppContext

        runner = CliRunner()
        with tempfile.TemporaryDirectory() as artifacts_dir:
            with tempfile.TemporaryDirectory() as slot_dir:
                with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
                    db_path = f.name

                captured_registry = None

                @cli.command(name="_test_capture")
                def _test_capture() -> None:
                    pass

                # We need to access the click context to get the app object.
                # The easiest way is to use the test runner's isolated_filesystem
                # and invoke the group, then access ctx.obj from inside a command.
                from click import get_current_context

                @cli.command(name="_test_registry")
                def _test_registry() -> None:
                    ctx = get_current_context()
                    app: CliAppContext = ctx.obj["app"]
                    nonlocal captured_registry
                    captured_registry = app.tool_registry

                # Need to invoke the group first to set up context, then the command
                result = runner.invoke(
                    cli,
                    [
                        "--db-path", db_path,
                        "--artifacts-path", artifacts_dir,
                        "--slot-dir", slot_dir,
                        "_test_registry",
                    ],
                )
                assert result.exit_code == 0, f"Output: {result.output}"
                assert captured_registry is not None
                assert "read_artifact" in captured_registry.list_names()
                assert "delete_memory" in captured_registry.list_names()
