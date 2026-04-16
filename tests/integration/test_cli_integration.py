"""CLI integration tests beyond --help.

These tests use Click's CliRunner to exercise actual command paths
with mocked dependencies where appropriate.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from hestia.cli import cli


@pytest.fixture
def cli_runner() -> CliRunner:
    """Provide a CliRunner instance."""
    return CliRunner()


@pytest.fixture
def temp_db_path() -> str:
    """Provide a temporary database path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    # Cleanup
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


@pytest.fixture
def temp_dir() -> str:
    """Provide a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestInitCommand:
    """Tests for `hestia init` command."""

    def test_init_creates_database(self, cli_runner: CliRunner, temp_db_path: str) -> None:
        """Run `hestia init`, verify DB file exists."""
        with tempfile.TemporaryDirectory() as artifacts_dir:
            with tempfile.TemporaryDirectory() as slot_dir:
                result = cli_runner.invoke(
                    cli,
                    [
                        "--db-path", temp_db_path,
                        "--artifacts-path", artifacts_dir,
                        "--slot-dir", slot_dir,
                        "init",
                    ],
                )

                assert result.exit_code == 0, f"Exit code: {result.exit_code}, output: {result.output}"
                assert "Initialized database" in result.output
                # Verify DB file was created
                assert Path(temp_db_path).exists()

    def test_init_creates_artifacts_directory(self, cli_runner: CliRunner, temp_db_path: str) -> None:
        """Verify init creates artifacts directory."""
        with tempfile.TemporaryDirectory() as artifacts_dir:
            with tempfile.TemporaryDirectory() as slot_dir:
                result = cli_runner.invoke(
                    cli,
                    [
                        "--db-path", temp_db_path,
                        "--artifacts-path", artifacts_dir,
                        "--slot-dir", slot_dir,
                        "init",
                    ],
                )

                assert result.exit_code == 0
                assert Path(artifacts_dir).exists()

    def test_init_creates_slot_directory(self, cli_runner: CliRunner, temp_db_path: str) -> None:
        """Verify init creates slot directory."""
        with tempfile.TemporaryDirectory() as artifacts_dir:
            with tempfile.TemporaryDirectory() as slot_dir:
                result = cli_runner.invoke(
                    cli,
                    [
                        "--db-path", temp_db_path,
                        "--artifacts-path", artifacts_dir,
                        "--slot-dir", slot_dir,
                        "init",
                    ],
                )

                assert result.exit_code == 0
                assert Path(slot_dir).exists()


class TestAskCommand:
    """Tests for `hestia ask` command."""

    def test_ask_command_exists(self, cli_runner: CliRunner) -> None:
        """Verify ask command exists and shows help."""
        result = cli_runner.invoke(cli, ["ask", "--help"])

        assert result.exit_code == 0
        assert "Send a single message" in result.output
        assert "MESSAGE" in result.output

    def test_ask_requires_message_argument(self, cli_runner: CliRunner) -> None:
        """Verify ask command requires a message argument."""
        result = cli_runner.invoke(cli, ["ask"])

        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Usage:" in result.output


class TestMemoryCommands:
    """Tests for `hestia memory` commands."""

    def test_memory_add_and_search(self, cli_runner: CliRunner, temp_db_path: str) -> None:
        """Add a memory via CLI, search for it, verify found."""
        with tempfile.TemporaryDirectory() as artifacts_dir:
            with tempfile.TemporaryDirectory() as slot_dir:
                # Init first
                result = cli_runner.invoke(
                    cli,
                    [
                        "--db-path", temp_db_path,
                        "--artifacts-path", artifacts_dir,
                        "--slot-dir", slot_dir,
                        "init",
                    ],
                )
                assert result.exit_code == 0

                # Add a memory
                result = cli_runner.invoke(
                    cli,
                    [
                        "--db-path", temp_db_path,
                        "--artifacts-path", artifacts_dir,
                        "--slot-dir", slot_dir,
                        "memory", "add",
                        "My favorite programming language is Python",
                        "--tags", "preferences programming",
                    ],
                )

                assert result.exit_code == 0
                assert "Saved:" in result.output

                # Extract the memory ID from output
                memory_id = result.output.strip().split("Saved:")[-1].strip()
                assert memory_id

                # Search for the memory
                result = cli_runner.invoke(
                    cli,
                    [
                        "--db-path", temp_db_path,
                        "--artifacts-path", artifacts_dir,
                        "--slot-dir", slot_dir,
                        "memory", "search", "programming language",
                    ],
                )

                assert result.exit_code == 0
                assert "Python" in result.output

    def test_memory_list_shows_memories(self, cli_runner: CliRunner, temp_db_path: str) -> None:
        """Add memories, list them, verify they appear."""
        with tempfile.TemporaryDirectory() as artifacts_dir:
            with tempfile.TemporaryDirectory() as slot_dir:
                # Init
                result = cli_runner.invoke(
                    cli,
                    [
                        "--db-path", temp_db_path,
                        "--artifacts-path", artifacts_dir,
                        "--slot-dir", slot_dir,
                        "init",
                    ],
                )
                assert result.exit_code == 0

                # Add a memory
                result = cli_runner.invoke(
                    cli,
                    [
                        "--db-path", temp_db_path,
                        "--artifacts-path", artifacts_dir,
                        "--slot-dir", slot_dir,
                        "memory", "add",
                        "Test memory content",
                    ],
                )
                assert result.exit_code == 0

                # List memories
                result = cli_runner.invoke(
                    cli,
                    [
                        "--db-path", temp_db_path,
                        "--artifacts-path", artifacts_dir,
                        "--slot-dir", slot_dir,
                        "memory", "list",
                    ],
                )

                assert result.exit_code == 0
                assert "Test memory content" in result.output

    def test_memory_remove_deletes_memory(self, cli_runner: CliRunner, temp_db_path: str) -> None:
        """Add a memory, remove it, verify it's gone."""
        with tempfile.TemporaryDirectory() as artifacts_dir:
            with tempfile.TemporaryDirectory() as slot_dir:
                # Init
                result = cli_runner.invoke(
                    cli,
                    [
                        "--db-path", temp_db_path,
                        "--artifacts-path", artifacts_dir,
                        "--slot-dir", slot_dir,
                        "init",
                    ],
                )
                assert result.exit_code == 0

                # Add a memory
                result = cli_runner.invoke(
                    cli,
                    [
                        "--db-path", temp_db_path,
                        "--artifacts-path", artifacts_dir,
                        "--slot-dir", slot_dir,
                        "memory", "add",
                        "Memory to delete",
                    ],
                )
                assert result.exit_code == 0
                memory_id = result.output.strip().split("Saved:")[-1].strip()

                # Remove it
                result = cli_runner.invoke(
                    cli,
                    [
                        "--db-path", temp_db_path,
                        "--artifacts-path", artifacts_dir,
                        "--slot-dir", slot_dir,
                        "memory", "remove", memory_id,
                    ],
                )

                assert result.exit_code == 0
                assert "Deleted:" in result.output

                # Verify it's gone by searching
                result = cli_runner.invoke(
                    cli,
                    [
                        "--db-path", temp_db_path,
                        "--artifacts-path", artifacts_dir,
                        "--slot-dir", slot_dir,
                        "memory", "search", "delete",
                    ],
                )

                # Should show no results
                assert result.exit_code == 0
                assert "No memories found" in result.output


class TestScheduleCommands:
    """Tests for `hestia schedule` commands."""

    def test_schedule_add_and_list(self, cli_runner: CliRunner, temp_db_path: str) -> None:
        """Add a scheduled task, list tasks, verify it appears."""
        with tempfile.TemporaryDirectory() as artifacts_dir:
            with tempfile.TemporaryDirectory() as slot_dir:
                # Init
                result = cli_runner.invoke(
                    cli,
                    [
                        "--db-path", temp_db_path,
                        "--artifacts-path", artifacts_dir,
                        "--slot-dir", slot_dir,
                        "init",
                    ],
                )
                assert result.exit_code == 0

                # Schedule a task for tomorrow
                from datetime import datetime, timedelta, timezone
                future_time = (datetime.now(timezone.utc) + timedelta(days=1)).strftime(
                    "%Y-%m-%dT%H:%M:%S"
                )

                result = cli_runner.invoke(
                    cli,
                    [
                        "--db-path", temp_db_path,
                        "--artifacts-path", artifacts_dir,
                        "--slot-dir", slot_dir,
                        "schedule", "add",
                        "--at", future_time,
                        "--description", "Test scheduled task",
                        "What is the current time?",
                    ],
                )

                assert result.exit_code == 0
                assert "Created task:" in result.output

                # List tasks
                result = cli_runner.invoke(
                    cli,
                    [
                        "--db-path", temp_db_path,
                        "--artifacts-path", artifacts_dir,
                        "--slot-dir", slot_dir,
                        "schedule", "list",
                    ],
                )

                assert result.exit_code == 0
                assert "Test scheduled task" in result.output

    def test_schedule_add_rejects_past_time(self, cli_runner: CliRunner, temp_db_path: str) -> None:
        """Verify scheduling in the past is rejected."""
        with tempfile.TemporaryDirectory() as artifacts_dir:
            with tempfile.TemporaryDirectory() as slot_dir:
                # Init
                result = cli_runner.invoke(
                    cli,
                    [
                        "--db-path", temp_db_path,
                        "--artifacts-path", artifacts_dir,
                        "--slot-dir", slot_dir,
                        "init",
                    ],
                )
                assert result.exit_code == 0

                # Try to schedule in the past
                from datetime import datetime, timedelta, timezone
                past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
                    "%Y-%m-%dT%H:%M:%S"
                )

                result = cli_runner.invoke(
                    cli,
                    [
                        "--db-path", temp_db_path,
                        "--artifacts-path", artifacts_dir,
                        "--slot-dir", slot_dir,
                        "schedule", "add",
                        "--at", past_time,
                        "Test prompt",
                    ],
                )

                assert result.exit_code == 1
                assert "past" in result.output.lower()


class TestHealthCommand:
    """Tests for `hestia health` command."""

    def test_health_reports_failure_when_no_server(self, cli_runner: CliRunner, temp_db_path: str) -> None:
        """No inference server running, verify error output."""
        with tempfile.TemporaryDirectory() as artifacts_dir:
            with tempfile.TemporaryDirectory() as slot_dir:
                # Init
                result = cli_runner.invoke(
                    cli,
                    [
                        "--db-path", temp_db_path,
                        "--artifacts-path", artifacts_dir,
                        "--slot-dir", slot_dir,
                        "--inference-url", "http://localhost:59999",  # Non-existent server
                        "init",
                    ],
                )
                assert result.exit_code == 0

                # Check health - should fail
                result = cli_runner.invoke(
                    cli,
                    [
                        "--db-path", temp_db_path,
                        "--artifacts-path", artifacts_dir,
                        "--slot-dir", slot_dir,
                        "--inference-url", "http://localhost:59999",
                        "health",
                    ],
                )

                assert result.exit_code == 1
                assert "failed" in result.output.lower() or "error" in result.output.lower()


class TestCliHelp:
    """Extended help command tests."""

    def test_main_help_shows_commands(self, cli_runner: CliRunner) -> None:
        """Main --help shows available commands."""
        result = cli_runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "init" in result.output
        assert "ask" in result.output
        assert "chat" in result.output
        assert "health" in result.output
        assert "version" in result.output
        assert "status" in result.output

    def test_memory_help_shows_subcommands(self, cli_runner: CliRunner) -> None:
        """memory --help shows subcommands."""
        result = cli_runner.invoke(cli, ["memory", "--help"])

        assert result.exit_code == 0
        assert "add" in result.output
        assert "search" in result.output
        assert "list" in result.output
        assert "remove" in result.output

    def test_schedule_help_shows_subcommands(self, cli_runner: CliRunner) -> None:
        """schedule --help shows subcommands."""
        result = cli_runner.invoke(cli, ["schedule", "--help"])

        assert result.exit_code == 0
        assert "add" in result.output
        assert "list" in result.output
        assert "remove" in result.output
        assert "enable" in result.output
        assert "disable" in result.output


class TestStatusCommand:
    """Extended status command tests."""

    def test_status_shows_sections(self, cli_runner: CliRunner, temp_db_path: str) -> None:
        """Status shows all expected sections."""
        with tempfile.TemporaryDirectory() as artifacts_dir:
            with tempfile.TemporaryDirectory() as slot_dir:
                # Init
                result = cli_runner.invoke(
                    cli,
                    [
                        "--db-path", temp_db_path,
                        "--artifacts-path", artifacts_dir,
                        "--slot-dir", slot_dir,
                        "init",
                    ],
                )
                assert result.exit_code == 0

                # Get status
                result = cli_runner.invoke(
                    cli,
                    [
                        "--db-path", temp_db_path,
                        "--artifacts-path", artifacts_dir,
                        "--slot-dir", slot_dir,
                        "--inference-url", "http://localhost:59999",
                        "status",
                    ],
                )

                # Should show sections even if inference is down
                assert result.exit_code == 0
                assert "Inference:" in result.output
                assert "Sessions:" in result.output
                assert "Turns (last 24h):" in result.output
                assert "Scheduled Tasks:" in result.output
                assert "Failures (last 24h):" in result.output
