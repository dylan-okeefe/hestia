"""Integration test for `hestia reflection status`."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from hestia.cli import cli
from hestia.reflection.scheduler import ReflectionScheduler


@pytest.fixture
def cli_runner() -> CliRunner:
    """Provide a CliRunner instance."""
    return CliRunner()


class TestReflectionStatusCommand:
    """Tests for `hestia reflection status`."""

    def test_status_shows_ok_when_no_failures(self, cli_runner: CliRunner, tmp_path: str) -> None:
        """Fresh scheduler shows ok status."""
        result = cli_runner.invoke(
            cli,
            [
                "--db-path", str(tmp_path / "test.db"),
                "--artifacts-path", str(tmp_path / "artifacts"),
                "--slot-dir", str(tmp_path / "slots"),
                "reflection",
                "status",
            ],
        )
        assert result.exit_code == 0
        assert "ok" in result.output.lower() or "0 failure" in result.output.lower()

    def test_status_shows_failure_after_forced_error(self, cli_runner: CliRunner, tmp_path: str) -> None:
        """After a forced failure, stdout contains failure type and count."""
        original_init = ReflectionScheduler.__init__

        def patched_init(self: ReflectionScheduler, *args: object, **kwargs: object) -> None:
            original_init(self, *args, **kwargs)
            self._record_failure("mining", RuntimeError("forced test failure"))

        with patch.object(ReflectionScheduler, "__init__", patched_init):
            result = cli_runner.invoke(
                cli,
                [
                    "--db-path", str(tmp_path / "test.db"),
                    "--artifacts-path", str(tmp_path / "artifacts"),
                    "--slot-dir", str(tmp_path / "slots"),
                    "reflection",
                    "status",
                ],
            )

        assert result.exit_code == 0
        assert "degraded" in result.output.lower() or "1 failure" in result.output.lower()
        assert "RuntimeError" in result.output
        assert "forced test failure" in result.output
