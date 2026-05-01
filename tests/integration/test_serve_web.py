"""Integration tests for `hestia serve` with web dashboard enabled."""

from __future__ import annotations

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


class TestServeWeb:
    """Tests for `hestia serve` with web dashboard."""

    def test_serve_starts_uvicorn_when_web_enabled(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Verify `hestia serve` starts uvicorn server when web.enabled=True."""
        db_path = str(tmp_path / "test.db")
        config_path = tmp_path / "config.py"
        config_path.write_text(
            'from hestia.config import HestiaConfig, WebConfig\n'
            'config = HestiaConfig(web=WebConfig(enabled=True, port=9876))\n'
        )

        with patch("hestia.commands.serve.uvicorn.Server") as mock_server_class:
            mock_server = MagicMock()
            mock_server.serve = AsyncMock(side_effect=KeyboardInterrupt)
            mock_server_class.return_value = mock_server

            with patch("hestia.platforms.runners.run_telegram"):
                with patch("hestia.platforms.runners.run_matrix"):
                    result = cli_runner.invoke(
                        cli,
                        ["--config", str(config_path), "--db-path", db_path, "serve"],
                    )

        assert result.exit_code == 0, f"Exit code: {result.exit_code}, output: {result.output}"
        mock_server_class.assert_called_once()
        call_args = mock_server_class.call_args
        config_arg = call_args[0][0]
        assert config_arg.host == "127.0.0.1"
        assert config_arg.port == 9876
        mock_server.serve.assert_awaited_once()
        assert "Dashboard available at http://127.0.0.1:9876" in result.output

    def test_serve_skips_web_when_disabled(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Verify `hestia serve` does not start uvicorn when web.enabled=False."""
        db_path = str(tmp_path / "test.db")
        config_path = tmp_path / "config.py"
        config_path.write_text(
            'from hestia.config import HestiaConfig\n'
            'config = HestiaConfig()\n'
        )

        with patch("hestia.commands.serve.uvicorn.Server") as mock_server_class:
            with patch("hestia.platforms.runners.run_telegram"):
                with patch("hestia.platforms.runners.run_matrix"):
                    result = cli_runner.invoke(
                        cli,
                        ["--config", str(config_path), "--db-path", db_path, "serve"],
                    )

        assert result.exit_code == 0, f"Exit code: {result.exit_code}, output: {result.output}"
        mock_server_class.assert_not_called()
        assert "No platforms or web server configured" in result.output
