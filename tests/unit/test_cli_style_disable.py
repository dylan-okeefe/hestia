"""Unit tests for `hestia style disable` command."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from hestia.cli import cli


class TestStyleDisableCommand:
    """Tests for `hestia style disable`."""

    def test_style_disable_invokes_without_error(self):
        """style disable exits 0 and prints confirmation."""
        runner = CliRunner()
        mock_app = MagicMock()
        mock_app.config.style.enabled = True
        with patch("hestia.cli.make_app", return_value=mock_app):
            result = runner.invoke(cli, ["style", "disable"])
        assert result.exit_code == 0, f"Output: {result.output}"
        assert "disabled" in result.output.lower()

    def test_style_disable_mutates_in_memory_only(self):
        """style disable sets app.config.style.enabled to False."""
        runner = CliRunner()
        mock_app = MagicMock()
        mock_app.config.style.enabled = True
        with patch("hestia.cli.make_app", return_value=mock_app):
            result = runner.invoke(cli, ["style", "disable"])
        assert result.exit_code == 0
        assert mock_app.config.style.enabled is False

    def test_style_disable_documents_persistence(self):
        """style disable --help mentions config file and env var."""
        runner = CliRunner()
        mock_app = MagicMock()
        mock_app.config.style.enabled = True
        with patch("hestia.cli.make_app", return_value=mock_app):
            result = runner.invoke(cli, ["style", "disable", "--help"])
        assert result.exit_code == 0
        assert "config" in result.output.lower()
        assert "HESTIA_STYLE_ENABLED" in result.output
