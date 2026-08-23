"""Tests for the external tool module ``setup(context)`` hook."""

from __future__ import annotations

import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pytest import LogCaptureFixture

from hestia.app import AppContext
from hestia.config import HestiaConfig, InferenceConfig, StorageConfig, TrustConfig
from hestia.core.types import Session, SessionState, SessionTemperature
from hestia.policy.constants import PLATFORM_SUBAGENT
from hestia.policy.default import DefaultPolicyEngine
from hestia.tools.external_context import ExternalToolModuleContext


def _ext_ctx():
    from hestia.policy.channel import Channel
    from hestia.tools.context import ToolCallContext

    return ToolCallContext(
        channel=Channel.API, mode="internal", internal_reason="unit-test"
    )


# Make tests/fixtures/external_tool_module importable as a top-level package.
_FIXTURES_ROOT = Path(__file__).parents[2] / "fixtures"
if str(_FIXTURES_ROOT) not in sys.path:
    sys.path.insert(0, str(_FIXTURES_ROOT))


def _make_app(tmp_path: Path, extra_tool_modules: list[str]) -> AppContext:
    """Build an AppContext configured for unit tests (no DB/inference)."""
    os.environ["HESTIA_ALLOW_DUMMY_MODEL"] = "1"
    cfg = HestiaConfig(
        inference=InferenceConfig(model_name="dummy"),
        storage=StorageConfig(
            artifacts_dir=tmp_path / "artifacts",
            database_url="sqlite+aiosqlite:///:memory:",
        ),
        extra_tool_modules=extra_tool_modules,
    )
    return AppContext(cfg)


@pytest.mark.asyncio
async def test_setup_runs_before_register(tmp_path: Path) -> None:
    """``setup`` populates the store before ``register`` exposes the tool."""
    app = _make_app(tmp_path, ["external_tool_module.setup_tools"])
    app.register_tools()

    assert "external_store_read" in app.tool_registry.list_names()
    result = await app.tool_registry.call("external_store_read", {"key": "greeting"}, context=_ext_ctx())
    assert result.content == "hello from setup"


def test_setup_failure_logs_warning_and_skips_register(
    caplog: LogCaptureFixture, tmp_path: Path
) -> None:
    """A failing ``setup`` logs a warning and prevents ``register`` from running."""
    app = _make_app(tmp_path, ["external_tool_module.setup_fails"])

    with caplog.at_level(logging.WARNING, logger="hestia.app"):
        app.register_tools()

    assert "setup failed" in caplog.text
    assert "external_store_read" not in app.tool_registry.list_names()


def test_missing_setup_still_allows_register(tmp_path: Path) -> None:
    """Modules without ``setup`` still work via ``register`` (L240 backward compat)."""
    app = _make_app(tmp_path, ["external_tool_module.tools"])
    app.register_tools()

    assert "external_echo" in app.tool_registry.list_names()


def test_context_exposes_db_and_config(tmp_path: Path) -> None:
    """The context object exposes the database handle and config."""
    import external_tool_module.setup_tools as setup_module  # type: ignore[import-not-found]

    app = _make_app(tmp_path, ["external_tool_module.setup_tools"])
    app.register_tools()

    assert setup_module.module_context is not None
    assert isinstance(setup_module.module_context, ExternalToolModuleContext)
    assert setup_module.module_context.db is app.db
    assert setup_module.module_context.config is app.config


def test_setup_tools_filtered_for_subagent(tmp_path: Path) -> None:
    """Tools registered after setup are still filtered by capability for subagents."""
    app = _make_app(tmp_path, ["external_tool_module.setup_tools"])
    app.register_tools()

    policy = DefaultPolicyEngine(trust=TrustConfig())
    session = Session(
        id="sub-1",
        platform=PLATFORM_SUBAGENT,
        platform_user="tester",
        started_at=datetime.now(UTC),
        last_active_at=datetime.now(UTC),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )
    names = app.tool_registry.list_names()
    filtered = policy.filter_tools(session, names, app.tool_registry)

    assert "external_store_shell" in names
    assert "external_store_shell" not in filtered
    assert "external_store_read" in filtered
