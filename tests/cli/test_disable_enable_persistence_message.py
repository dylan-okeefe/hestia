"""Tests that process-local *_disable commands clarify their in-memory-only semantics."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from hestia.cli import cli
from hestia.memory import MemoryEpochCompiler


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def make_app(tmp_path):
    """Build a minimal CliAppContext for disable/enable CLI tests."""

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


def test_style_disable_clarifies_process_only(
    runner: CliRunner, make_app, monkeypatch
) -> None:
    """style disable must mention 'this process' and the config path to persist."""
    from hestia import cli as cli_module
    from hestia.config import HestiaConfig

    cfg = HestiaConfig.default()
    app = make_app(cfg)
    monkeypatch.setattr(cli_module, "make_app", lambda _: app)

    result = runner.invoke(cli, ["style", "disable"])
    assert result.exit_code == 0
    assert "this process" in result.output.lower()
    assert "style.enabled" in result.output or "config" in result.output.lower()
