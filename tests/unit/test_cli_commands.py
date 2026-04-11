"""Tests for CLI commands (version, status, failures)."""

from click.testing import CliRunner

from hestia.cli import cli


class TestVersionCommand:
    """Tests for hestia version."""

    def test_version_shows_package_version(self):
        """version command shows package version."""
        runner = CliRunner()
        result = runner.invoke(cli, ["version"])
        assert result.exit_code == 0
        assert "Hestia" in result.output
        assert "Python" in result.output


class TestStatusCommandExists:
    """Basic tests for hestia status command existence."""

    def test_status_help_shows_options(self):
        """status --help shows usage."""
        runner = CliRunner()
        result = runner.invoke(cli, ["status", "--help"])
        assert result.exit_code == 0
        assert "Show system status summary" in result.output


class TestFailuresCommandExists:
    """Basic tests for hestia failures command existence."""

    def test_failures_list_help(self):
        """failures list --help shows usage."""
        runner = CliRunner()
        result = runner.invoke(cli, ["failures", "list", "--help"])
        assert result.exit_code == 0
        assert "List recent failures" in result.output

    def test_failures_summary_help(self):
        """failures summary --help shows usage."""
        runner = CliRunner()
        result = runner.invoke(cli, ["failures", "summary", "--help"])
        assert result.exit_code == 0
        assert "Show failure counts by class" in result.output

    def test_failures_group_exists(self):
        """failures group has subcommands."""
        runner = CliRunner()
        result = runner.invoke(cli, ["failures", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "summary" in result.output
