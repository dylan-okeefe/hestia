"""Integration test for missing SOUL.md / calibration warnings."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from hestia.cli import cli


@pytest.fixture
def cli_runner() -> CliRunner:
    """Provide a CliRunner instance."""
    return CliRunner()


class TestMissingSoulWarning:
    """Tests that CLI warns when SOUL.md or calibration is missing."""

    def test_missing_soul_path_warns(self, cli_runner: CliRunner, tmp_path: str, monkeypatch: pytest.MonkeyPatch) -> None:
        """Running a command with a non-existent HESTIA_SOUL_PATH prints a warning."""
        monkeypatch.setenv("HESTIA_SOUL_PATH", "/nonexistent/SOUL.md")

        result = cli_runner.invoke(
            cli,
            [
                "--db-path", str(tmp_path / "test.db"),
                "--artifacts-path", str(tmp_path / "artifacts"),
                "--slot-dir", str(tmp_path / "slots"),
                "init",
            ],
        )

        assert result.exit_code == 0
        assert "/nonexistent/SOUL.md" in result.output
        assert "Warning" in result.output

    def test_missing_calibration_warns(self, cli_runner: CliRunner, tmp_path: str, monkeypatch: pytest.MonkeyPatch) -> None:
        """Running a command with a non-existent HESTIA_CALIBRATION_PATH prints a warning."""
        monkeypatch.setenv("HESTIA_CALIBRATION_PATH", "/nonexistent/calibration.json")

        result = cli_runner.invoke(
            cli,
            [
                "--db-path", str(tmp_path / "test.db"),
                "--artifacts-path", str(tmp_path / "artifacts"),
                "--slot-dir", str(tmp_path / "slots"),
                "init",
            ],
        )

        assert result.exit_code == 0
        assert "/nonexistent/calibration.json" in result.output
        assert "Warning" in result.output
