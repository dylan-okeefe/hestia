"""End-to-end tests for hestia audit command via CliRunner."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from hestia.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def make_app(tmp_path):
    """Build a minimal CliAppContext for audit CLI tests."""

    def _factory(cfg=None):
        from hestia.app import AppContext
        from hestia.config import HestiaConfig
        if cfg is None:
            cfg = HestiaConfig.default()
        cfg.storage.database_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
        cfg.storage.artifacts_dir = tmp_path / "artifacts"
        app = AppContext(cfg)
        return app

    return _factory


class TestAuditCommand:
    """End-to-end tests for the audit CLI command."""

    def test_audit_runs_and_exits_zero_on_clean_env(self, runner, make_app, monkeypatch):
        """Mock audit to return no critical/warning findings; assert exit 0."""
        from hestia import cli as cli_module
        from hestia.audit.checks import AuditReport

        app = make_app()
        monkeypatch.setattr(cli_module, "make_app", lambda cfg: app)

        async def clean_audit(app):
            report = AuditReport()
            report.add_finding("info", "test", "Everything looks fine")
            return report

        monkeypatch.setattr("hestia.audit.SecurityAuditor.run_audit", clean_audit)
        result = runner.invoke(cli, ["audit", "run"])
        assert result.exit_code == 0
        assert "Everything looks fine" in result.output

    def test_audit_exits_one_on_critical_findings(self, runner, make_app, monkeypatch):
        """Mock audit to return a critical finding; assert exit 1."""
        from hestia import cli as cli_module
        from hestia.audit.checks import AuditReport

        app = make_app()
        monkeypatch.setattr(cli_module, "make_app", lambda cfg: app)

        async def critical_audit(app):
            report = AuditReport()
            report.add_finding("critical", "config", "Telegram bot has empty allowed_users")
            return report

        monkeypatch.setattr("hestia.audit.SecurityAuditor.run_audit", critical_audit)
        result = runner.invoke(cli, ["audit", "run"])
        assert result.exit_code == 1
        assert "Telegram bot has empty allowed_users" in result.output

    def test_audit_strict_exits_one_on_warnings(self, runner, make_app, monkeypatch):
        """With --strict, a warning finding should cause exit 1."""
        from hestia import cli as cli_module
        from hestia.audit.checks import AuditReport

        app = make_app()
        monkeypatch.setattr(cli_module, "make_app", lambda cfg: app)

        async def warning_audit(app):
            report = AuditReport()
            report.add_finding("warning", "sandbox", "Relative path '.' in allowed_roots")
            return report

        monkeypatch.setattr("hestia.audit.SecurityAuditor.run_audit", warning_audit)
        result = runner.invoke(cli, ["audit", "run", "--strict"])
        assert result.exit_code == 1
        assert "Relative path" in result.output
        assert "Strict mode:" in result.output

    def test_audit_strict_exits_zero_on_info_only(self, runner, make_app, monkeypatch):
        """With --strict, info-only findings should still exit 0."""
        from hestia import cli as cli_module
        from hestia.audit.checks import AuditReport

        app = make_app()
        monkeypatch.setattr(cli_module, "make_app", lambda cfg: app)

        async def info_audit(app):
            report = AuditReport()
            report.add_finding("info", "dependencies", "pip-audit not installed")
            return report

        monkeypatch.setattr("hestia.audit.SecurityAuditor.run_audit", info_audit)
        result = runner.invoke(cli, ["audit", "run", "--strict"])
        assert result.exit_code == 0
        assert "pip-audit not installed" in result.output
        assert "Strict mode:" in result.output

    def test_audit_strict_short_flag(self, runner, make_app, monkeypatch):
        """The -s short flag should work identically to --strict."""
        from hestia import cli as cli_module
        from hestia.audit.checks import AuditReport

        app = make_app()
        monkeypatch.setattr(cli_module, "make_app", lambda cfg: app)

        async def warning_audit(app):
            report = AuditReport()
            report.add_finding("warning", "config", "Matrix access_token set but user_id missing")
            return report

        monkeypatch.setattr("hestia.audit.SecurityAuditor.run_audit", warning_audit)
        result = runner.invoke(cli, ["audit", "run", "-s"])
        assert result.exit_code == 1
        assert "Strict mode:" in result.output

    def test_audit_default_allows_warnings(self, runner, make_app, monkeypatch):
        """Without --strict, warnings should not cause exit 1."""
        from hestia import cli as cli_module
        from hestia.audit.checks import AuditReport

        app = make_app()
        monkeypatch.setattr(cli_module, "make_app", lambda cfg: app)

        async def warning_audit(app):
            report = AuditReport()
            report.add_finding("warning", "sandbox", "Relative path '.' in allowed_roots")
            return report

        monkeypatch.setattr("hestia.audit.SecurityAuditor.run_audit", warning_audit)
        result = runner.invoke(cli, ["audit", "run"])
        assert result.exit_code == 0
        assert "Relative path" in result.output
        assert "Strict mode:" not in result.output
