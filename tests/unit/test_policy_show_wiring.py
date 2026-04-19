"""L35b wiring: policy show derives from live registry and config."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from hestia.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def make_app(tmp_path):
    """Build a minimal CliAppContext for policy show tests."""

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
        return CliAppContext(
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
            skill_store=skill_store,
        )

    return _factory


def test_policy_show_reflects_registered_confirmation_tools(runner, make_app, monkeypatch):
    """A tool with requires_confirmation=True must appear in the confirmation list."""
    from hestia import cli as cli_module
    from hestia.tools.metadata import tool

    app = make_app()

    @tool(name="fake_confirm_tool", public_description="fake", requires_confirmation=True)
    def fake_confirm_tool():
        pass

    app.tool_registry.register(fake_confirm_tool)
    monkeypatch.setattr(cli_module, "make_app", lambda cfg: app)
    result = runner.invoke(cli, ["policy", "show"])
    assert result.exit_code == 0
    assert "fake_confirm_tool" in result.output


def test_policy_show_reflects_zero_confirmation_tools(runner, make_app, monkeypatch):
    """When no tools require confirmation, '(none)' must be shown."""
    from hestia import cli as cli_module

    app = make_app()
    monkeypatch.setattr(cli_module, "make_app", lambda cfg: app)
    result = runner.invoke(cli, ["policy", "show"])
    assert result.exit_code == 0
    assert "(none)" in result.output


def test_policy_show_reads_retry_max_attempts_from_engine(runner, make_app, monkeypatch):
    """Max attempts must reflect the live policy engine attribute."""
    from hestia import cli as cli_module

    app = make_app()
    app.policy.retry_max_attempts = 5
    monkeypatch.setattr(cli_module, "make_app", lambda cfg: app)
    result = runner.invoke(cli, ["policy", "show"])
    assert result.exit_code == 0
    assert "Max attempts: 5" in result.output


def test_policy_show_reads_delegation_keywords_from_config(runner, make_app, monkeypatch):
    """Delegation keywords must come from PolicyConfig when set."""
    from hestia import cli as cli_module
    from hestia.config import HestiaConfig, PolicyConfig

    cfg = HestiaConfig.default()
    cfg.policy = PolicyConfig(delegation_keywords=("only_this", "and_this"))
    app = make_app(cfg)
    monkeypatch.setattr(cli_module, "make_app", lambda _: app)
    result = runner.invoke(cli, ["policy", "show"])
    assert result.exit_code == 0
    assert "only_this, and_this" in result.output


def test_policy_show_uses_default_keywords_when_config_none(runner, make_app, monkeypatch):
    """When PolicyConfig.delegation_keywords is None, defaults must be used."""
    from hestia import cli as cli_module
    from hestia.config import HestiaConfig, PolicyConfig

    cfg = HestiaConfig.default()
    cfg.policy = PolicyConfig(delegation_keywords=None)
    app = make_app(cfg)
    monkeypatch.setattr(cli_module, "make_app", lambda _: app)
    result = runner.invoke(cli, ["policy", "show"])
    assert result.exit_code == 0
    assert "research" in result.output


def test_policy_show_surfaces_trust_preset(runner, make_app, monkeypatch):
    """Trust preset name must be surfaced when set."""
    from hestia import cli as cli_module
    from hestia.config import HestiaConfig, TrustConfig

    cfg = HestiaConfig.default()
    cfg.trust = TrustConfig(preset="paranoid")
    app = make_app(cfg)
    monkeypatch.setattr(cli_module, "make_app", lambda _: app)
    result = runner.invoke(cli, ["policy", "show"])
    assert result.exit_code == 0
    assert "Active preset: paranoid" in result.output
