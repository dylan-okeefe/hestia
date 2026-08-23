"""Tests for the external-tool-modules extension point."""

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
async def test_external_tool_loads_and_calls(tmp_path: Path) -> None:
    """An external module's tool is registered and callable."""
    app = _make_app(tmp_path, ["external_tool_module.tools"])
    app.register_tools()

    assert "external_echo" in app.tool_registry.list_names()
    result = await app.tool_registry.call("external_echo", {"message": "hello"}, context=_ext_ctx())
    assert result.content == "hello"


def test_missing_register_warns_and_skips(caplog: LogCaptureFixture, tmp_path: Path) -> None:
    """A module with no register() callable logs a warning and adds no tools."""
    app = _make_app(tmp_path, ["external_tool_module.no_register"])

    with caplog.at_level(logging.WARNING, logger="hestia.app"):
        app.register_tools()

    assert "has no callable register" in caplog.text
    assert "external_noop" not in app.tool_registry.list_names()


def test_import_error_warns_and_skips(caplog: LogCaptureFixture, tmp_path: Path) -> None:
    """A non-existent module logs a warning and does not crash registration."""
    app = _make_app(tmp_path, ["definitely_not_a_real_module_12345"])

    with caplog.at_level(logging.WARNING, logger="hestia.app"):
        app.register_tools()

    assert "Failed to import" in caplog.text


def test_external_shell_filtered_for_subagent(tmp_path: Path) -> None:
    """External tools with SHELL_EXEC are filtered for subagent sessions."""
    app = _make_app(tmp_path, ["external_tool_module.tools"])
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

    assert "external_shell" in names
    assert "external_shell" not in filtered
    assert "external_echo" in filtered


def test_empty_extra_tool_modules_unchanged(tmp_path: Path) -> None:
    """An empty extra_tool_modules list leaves built-in registration unchanged."""
    app = _make_app(tmp_path, [])
    app.register_tools()

    names = app.tool_registry.list_names()
    assert "current_time" in names
    assert "external_echo" not in names


def test_extra_tool_modules_from_env() -> None:
    """The config field loads from HESTIA_EXTRA_TOOL_MODULES as a JSON list."""
    cfg = HestiaConfig.from_env(
        {"HESTIA_EXTRA_TOOL_MODULES": '["my_private_tools", "another.module"]'}
    )
    assert cfg.extra_tool_modules == ["my_private_tools", "another.module"]
