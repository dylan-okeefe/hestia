"""Tests that process-local *_disable commands clarify their in-memory-only semantics."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from hestia.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def make_app(tmp_path):
    """Build a minimal CliAppContext for disable/enable CLI tests."""

    def _factory(cfg=None):
        from hestia.app import AppContext
        from hestia.config import HestiaConfig
        from hestia.persistence.db import Database
        from hestia.persistence.skill_store import SkillStore

        if cfg is None:
            cfg = HestiaConfig.default()
        cfg.storage.database_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
        cfg.storage.artifacts_dir = tmp_path / "artifacts"
        db = Database(cfg.storage.database_url)
        skill_store = SkillStore(db)
        app = AppContext(cfg)
        app.skill_store = skill_store
        return app

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
