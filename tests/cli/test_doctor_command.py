"""End-to-end tests for hestia doctor command via CliRunner."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from hestia.cli import cli
from hestia.memory import MemoryEpochCompiler


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def make_app(tmp_path):
    """Build a minimal CliAppContext for doctor CLI tests."""

    def _factory(cfg=None):
        from hestia.app import CliAppContext
        from hestia.artifacts.store import ArtifactStore
        from hestia.config import HestiaConfig
        from hestia.memory import MemoryStore
        from hestia.persistence.db import Database
        from hestia.persistence.failure_store import FailureStore
        from hestia.persistence.scheduler import SchedulerStore
        from hestia.persistence.sessions import SessionStore
        from hestia.persistence.skill_store import SkillStore
        from hestia.persistence.trace_store import TraceStore
        from hestia.policy.default import DefaultPolicyEngine
        from hestia.tools.registry import ToolRegistry

        if cfg is None:
            cfg = HestiaConfig.default()
        cfg.storage.database_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
        cfg.storage.artifacts_dir = tmp_path / "artifacts"
        db = Database(cfg.storage.database_url)
        artifact_store = ArtifactStore(cfg.storage.artifacts_dir)
        session_store = SessionStore(db)
        tool_registry = ToolRegistry(artifact_store)
        policy = DefaultPolicyEngine()
        memory_store = MemoryStore(db)
        failure_store = FailureStore(db)
        trace_store = TraceStore(db)
        scheduler_store = SchedulerStore(db)
        skill_store = SkillStore(db)
        from hestia.app import CoreAppContext, FeatureAppContext

        core = CoreAppContext(
            config=cfg,
            db=db,
            session_store=session_store,
            tool_registry=tool_registry,
            policy=policy,
            memory_store=memory_store,
            failure_store=failure_store,
            trace_store=trace_store,
            artifact_store=artifact_store,
            scheduler_store=scheduler_store,
            epoch_compiler=MemoryEpochCompiler(memory_store, max_tokens=500),
        )
        features = FeatureAppContext(skill_store=skill_store)
        return CliAppContext(core=core, features=features)

    return _factory


class TestDoctorCommand:
    """End-to-end tests for the doctor CLI command."""

    def test_doctor_runs_and_exits_zero_on_clean_env(self, runner, make_app, monkeypatch):
        """Mock all checks to return ok; assert exit 0 and check names in output."""
        from hestia import cli as cli_module
        from hestia.doctor import CheckResult

        app = make_app()
        monkeypatch.setattr(cli_module, "make_app", lambda cfg: app)

        async def all_ok(app):
            return [
                CheckResult("python_version", True, ""),
                CheckResult("dependencies_in_sync", True, ""),
                CheckResult("config_file_loads", True, ""),
                CheckResult("config_schema", True, ""),
                CheckResult("sqlite_dbs_readable", True, ""),
                CheckResult("llamacpp_reachable", True, ""),
                CheckResult("platform_prereqs", True, ""),
                CheckResult("trust_preset_resolves", True, ""),
                CheckResult("memory_epoch", True, ""),
            ]

        monkeypatch.setattr("hestia.doctor.run_checks", all_ok)
        result = runner.invoke(cli, ["doctor"])
        assert result.exit_code == 0
        assert "python_version" in result.output
        assert "dependencies_in_sync" in result.output
        assert "config_file_loads" in result.output
        assert "config_schema" in result.output
        assert "sqlite_dbs_readable" in result.output
        assert "llamacpp_reachable" in result.output
        assert "platform_prereqs" in result.output
        assert "trust_preset_resolves" in result.output
        assert "memory_epoch" in result.output

    def test_doctor_exits_one_when_any_check_fails(self, runner, make_app, monkeypatch):
        """Patch one check to return ok=False; assert exit 1."""
        from hestia import cli as cli_module
        from hestia.doctor import CheckResult

        app = make_app()
        monkeypatch.setattr(cli_module, "make_app", lambda cfg: app)

        async def one_fails(app):
            return [
                CheckResult("python_version", True, ""),
                CheckResult("dependencies_in_sync", False, "drift detected"),
                CheckResult("config_file_loads", True, ""),
                CheckResult("config_schema", True, ""),
                CheckResult("sqlite_dbs_readable", True, ""),
                CheckResult("llamacpp_reachable", True, ""),
                CheckResult("platform_prereqs", True, ""),
                CheckResult("trust_preset_resolves", True, ""),
                CheckResult("memory_epoch", True, ""),
            ]

        monkeypatch.setattr("hestia.doctor.run_checks", one_fails)
        result = runner.invoke(cli, ["doctor"])
        assert result.exit_code == 1
        assert "dependencies_in_sync" in result.output

    def test_doctor_plain_uses_ascii_markers(self, runner, make_app, monkeypatch):
        """Invoke with --plain; assert [ok] or [FAIL] in output, unicode absent."""
        from hestia import cli as cli_module
        from hestia.doctor import CheckResult

        app = make_app()
        monkeypatch.setattr(cli_module, "make_app", lambda cfg: app)

        async def all_ok(app):
            return [CheckResult("python_version", True, "")]

        monkeypatch.setattr("hestia.doctor.run_checks", all_ok)
        result = runner.invoke(cli, ["doctor", "--plain"])
        assert result.exit_code == 0
        assert "[ok]" in result.output
        assert "✓" not in result.output
        assert "✗" not in result.output

    def test_doctor_default_uses_unicode_markers(self, runner, make_app, monkeypatch):
        """Invoke without --plain; assert ✓ or ✗ in output."""
        from hestia import cli as cli_module
        from hestia.doctor import CheckResult

        app = make_app()
        monkeypatch.setattr(cli_module, "make_app", lambda cfg: app)

        async def all_ok(app):
            return [CheckResult("python_version", True, "")]

        monkeypatch.setattr("hestia.doctor.run_checks", all_ok)
        result = runner.invoke(cli, ["doctor"])
        assert result.exit_code == 0
        assert "✓" in result.output
        assert "[ok]" not in result.output
