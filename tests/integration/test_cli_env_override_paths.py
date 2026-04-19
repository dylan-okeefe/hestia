"""Integration test for HESTIA_SOUL_PATH and HESTIA_CALIBRATION_PATH overrides."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from hestia.cli import cli


@pytest.fixture
def cli_runner() -> CliRunner:
    """Provide a CliRunner instance."""
    return CliRunner()


class TestEnvOverridePaths:
    """Tests that environment variables override default paths."""

    def test_soul_path_override_used(self, cli_runner: CliRunner, tmp_path: str, monkeypatch: pytest.MonkeyPatch) -> None:
        """HESTIA_SOUL_PATH pointing to an existing file produces no warning."""
        soul_file = tmp_path / "custom_soul.md"
        soul_file.write_text("# Custom personality\n")
        monkeypatch.setenv("HESTIA_SOUL_PATH", str(soul_file))

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
        assert "personality file not found" not in result.output.lower()

    def test_calibration_path_override_used(self, cli_runner: CliRunner, tmp_path: str, monkeypatch: pytest.MonkeyPatch) -> None:
        """HESTIA_CALIBRATION_PATH pointing to an existing file produces no warning."""
        cal_file = tmp_path / "custom_calibration.json"
        cal_file.write_text('{"body_factor": 1.2}')
        monkeypatch.setenv("HESTIA_CALIBRATION_PATH", str(cal_file))

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
        assert "calibration file not found" not in result.output.lower()
