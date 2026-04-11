"""Unit tests for CLI schedule commands."""

from datetime import datetime, timedelta

import pytest
from click.testing import CliRunner

from hestia.cli import cli


@pytest.fixture
def runner():
    """Create a CLI runner."""
    return CliRunner()


@pytest.fixture
def db_url(tmp_path):
    """Create a temporary database URL."""
    return f"sqlite+aiosqlite:///{tmp_path}/test.db"


class TestScheduleAdd:
    """Tests for `hestia schedule add` command."""

    def test_add_cron_task(self, runner, tmp_path):
        """Can add a cron-scheduled task."""
        db_path = tmp_path / "test.db"
        result = runner.invoke(
            cli,
            [
                "--db-path",
                str(db_path),
                "schedule",
                "add",
                "--cron",
                "0 9 * * 1-5",
                "--description",
                "Daily standup",
                "Summarize my morning messages",
            ],
        )
        assert result.exit_code == 0
        assert "Created task:" in result.output
        assert "cron" in result.output

    def test_add_one_shot_task(self, runner, tmp_path):
        """Can add a one-shot task."""
        db_path = tmp_path / "test.db"
        future = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        result = runner.invoke(
            cli,
            [
                "--db-path",
                str(db_path),
                "schedule",
                "add",
                "--at",
                future,
                "--description",
                "Coffee reminder",
                "Time for coffee",
            ],
        )
        assert result.exit_code == 0
        assert "Created task:" in result.output
        assert "at" in result.output

    def test_add_rejects_both_cron_and_at(self, runner, tmp_path):
        """Cannot specify both --cron and --at."""
        db_path = tmp_path / "test.db"
        future = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        result = runner.invoke(
            cli,
            [
                "--db-path",
                str(db_path),
                "schedule",
                "add",
                "--cron",
                "0 9 * * *",
                "--at",
                future,
                "Task with both",
            ],
        )
        assert result.exit_code == 1
        assert "Cannot specify both" in result.output

    def test_add_rejects_neither_cron_nor_at(self, runner, tmp_path):
        """Must specify either --cron or --at."""
        db_path = tmp_path / "test.db"
        result = runner.invoke(
            cli,
            [
                "--db-path",
                str(db_path),
                "schedule",
                "add",
                "--description",
                "No schedule",
                "Task with no schedule",
            ],
        )
        assert result.exit_code == 1
        assert "Must specify either" in result.output

    def test_add_rejects_past_time(self, runner, tmp_path):
        """Cannot schedule task in the past."""
        db_path = tmp_path / "test.db"
        past = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        result = runner.invoke(
            cli, ["--db-path", str(db_path), "schedule", "add", "--at", past, "Task in the past"]
        )
        assert result.exit_code == 1
        assert "Cannot schedule task in the past" in result.output

    def test_add_rejects_invalid_datetime(self, runner, tmp_path):
        """Invalid datetime format is rejected."""
        db_path = tmp_path / "test.db"
        result = runner.invoke(
            cli,
            [
                "--db-path",
                str(db_path),
                "schedule",
                "add",
                "--at",
                "not-a-date",
                "Task with bad date",
            ],
        )
        assert result.exit_code == 1
        assert "Invalid datetime format" in result.output


class TestScheduleList:
    """Tests for `hestia schedule list` command."""

    def test_list_empty(self, runner, tmp_path):
        """List shows message when no tasks exist."""
        db_path = tmp_path / "test.db"
        result = runner.invoke(cli, ["--db-path", str(db_path), "schedule", "list"])
        assert result.exit_code == 0
        assert "No scheduled tasks" in result.output

    def test_list_shows_tasks(self, runner, tmp_path):
        """List displays created tasks."""
        db_path = tmp_path / "test.db"
        # Add a task first
        runner.invoke(
            cli,
            [
                "--db-path",
                str(db_path),
                "schedule",
                "add",
                "--cron",
                "0 9 * * *",
                "--description",
                "Daily summary",
                "Summarize my day",
            ],
        )

        result = runner.invoke(cli, ["--db-path", str(db_path), "schedule", "list"])
        assert result.exit_code == 0
        assert "Daily summary" in result.output
        assert "cron" in result.output


class TestScheduleShow:
    """Tests for `hestia schedule show` command."""

    def test_show_existing_task(self, runner, tmp_path):
        """Can show details of an existing task."""
        db_path = tmp_path / "test.db"
        # Add a task
        result = runner.invoke(
            cli,
            [
                "--db-path",
                str(db_path),
                "schedule",
                "add",
                "--cron",
                "0 9 * * *",
                "--description",
                "Test task",
                "Test prompt",
            ],
        )

        # Extract task ID from output
        task_id = None
        for line in result.output.split("\n"):
            if line.startswith("Created task:"):
                task_id = line.split(":")[1].strip()
                break

        assert task_id is not None

        result = runner.invoke(cli, ["--db-path", str(db_path), "schedule", "show", task_id])
        assert result.exit_code == 0
        assert task_id in result.output
        assert "Test task" in result.output
        assert "Test prompt" in result.output

    def test_show_missing_task(self, runner, tmp_path):
        """Shows error for non-existent task."""
        db_path = tmp_path / "test.db"
        result = runner.invoke(
            cli, ["--db-path", str(db_path), "schedule", "show", "task_nonexistent"]
        )
        assert result.exit_code == 1
        assert "Task not found" in result.output


class TestScheduleDisable:
    """Tests for `hestia schedule disable` command."""

    def test_disable_existing_task(self, runner, tmp_path):
        """Can disable an existing task."""
        db_path = tmp_path / "test.db"
        # Add a task
        result = runner.invoke(
            cli,
            [
                "--db-path",
                str(db_path),
                "schedule",
                "add",
                "--cron",
                "0 9 * * *",
                "Task to disable",
            ],
        )

        # Extract task ID
        task_id = None
        for line in result.output.split("\n"):
            if line.startswith("Created task:"):
                task_id = line.split(":")[1].strip()
                break

        assert task_id is not None

        result = runner.invoke(cli, ["--db-path", str(db_path), "schedule", "disable", task_id])
        assert result.exit_code == 0
        assert f"Task {task_id} disabled" in result.output

    def test_disable_missing_task(self, runner, tmp_path):
        """Shows error for non-existent task."""
        db_path = tmp_path / "test.db"
        result = runner.invoke(
            cli, ["--db-path", str(db_path), "schedule", "disable", "task_nonexistent"]
        )
        assert result.exit_code == 1
        assert "Task not found" in result.output


class TestScheduleRemove:
    """Tests for `hestia schedule remove` command."""

    def test_remove_existing_task(self, runner, tmp_path):
        """Can remove an existing task."""
        db_path = tmp_path / "test.db"
        # Add a task
        result = runner.invoke(
            cli,
            ["--db-path", str(db_path), "schedule", "add", "--cron", "0 9 * * *", "Task to remove"],
        )

        # Extract task ID
        task_id = None
        for line in result.output.split("\n"):
            if line.startswith("Created task:"):
                task_id = line.split(":")[1].strip()
                break

        assert task_id is not None

        result = runner.invoke(cli, ["--db-path", str(db_path), "schedule", "remove", task_id])
        assert result.exit_code == 0
        assert f"Task {task_id} removed" in result.output

    def test_remove_missing_task(self, runner, tmp_path):
        """Shows error for non-existent task."""
        db_path = tmp_path / "test.db"
        result = runner.invoke(
            cli, ["--db-path", str(db_path), "schedule", "remove", "task_nonexistent"]
        )
        assert result.exit_code == 1
        assert "Task not found" in result.output
