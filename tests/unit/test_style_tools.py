"""Unit tests for style tools."""

from __future__ import annotations

import pytest

from hestia.persistence.db import Database
from hestia.runtime_context import current_platform, current_platform_user
from hestia.style.store import StyleProfileStore
from hestia.tools.builtin.style_tools import (
    make_reset_style_metric_tool,
    make_reset_style_profile_tool,
    make_show_style_profile_tool,
)


class TestStyleTools:
    @pytest.fixture
    async def tools(self, tmp_path):
        """Create style tools bound to a fresh StyleProfileStore."""
        db = Database(f"sqlite+aiosqlite:///{tmp_path}/test.db")
        await db.connect()
        await db.create_tables()
        store = StyleProfileStore(db)
        await store.create_table()

        show_tool = make_show_style_profile_tool(store)
        reset_metric_tool = make_reset_style_metric_tool(store)
        reset_profile_tool = make_reset_style_profile_tool(store)

        yield store, show_tool, reset_metric_tool, reset_profile_tool
        await db.close()

    @pytest.mark.asyncio
    async def test_show_style_profile_no_context(self, tools):
        """show_style_profile returns error when no runtime context."""
        _, show_tool, _, _ = tools
        result = await show_tool()
        assert "No platform identity" in result

    @pytest.mark.asyncio
    async def test_show_style_profile_with_context(self, tools):
        """show_style_profile returns metrics when context is set."""
        store, show_tool, _, _ = tools
        await store.set_metric("cli", "alice", "formality", 0.75)
        await store.set_metric("cli", "alice", "preferred_length", 150)

        platform_token = current_platform.set("cli")
        user_token = current_platform_user.set("alice")
        try:
            result = await show_tool()
            assert "cli:alice" in result
            assert "formality" in result
            assert "preferred_length" in result
        finally:
            current_platform.reset(platform_token)
            current_platform_user.reset(user_token)

    @pytest.mark.asyncio
    async def test_show_style_profile_empty(self, tools):
        """show_style_profile returns message when no metrics exist."""
        _, show_tool, _, _ = tools
        platform_token = current_platform.set("cli")
        user_token = current_platform_user.set("bob")
        try:
            result = await show_tool()
            assert "No style profile found" in result
        finally:
            current_platform.reset(platform_token)
            current_platform_user.reset(user_token)

    @pytest.mark.asyncio
    async def test_reset_style_metric_no_context(self, tools):
        """reset_style_metric returns error when no runtime context."""
        _, _, reset_metric_tool, _ = tools
        result = await reset_metric_tool("formality")
        assert "No platform identity" in result

    @pytest.mark.asyncio
    async def test_reset_style_metric(self, tools):
        """reset_style_metric resets a single metric."""
        store, _, reset_metric_tool, _ = tools
        await store.set_metric("cli", "alice", "formality", 0.75)

        platform_token = current_platform.set("cli")
        user_token = current_platform_user.set("alice")
        try:
            result = await reset_metric_tool("formality")
            assert "Reset metric 'formality'" in result

            metric = await store.get_metric("cli", "alice", "formality")
            assert metric is not None
            assert metric.value_json == "null"
        finally:
            current_platform.reset(platform_token)
            current_platform_user.reset(user_token)

    @pytest.mark.asyncio
    async def test_reset_style_profile_no_context(self, tools):
        """reset_style_profile returns error when no runtime context."""
        _, _, _, reset_profile_tool = tools
        result = await reset_profile_tool()
        assert "No platform identity" in result

    @pytest.mark.asyncio
    async def test_reset_style_profile(self, tools):
        """reset_style_profile deletes all metrics for the user."""
        store, _, _, reset_profile_tool = tools
        await store.set_metric("cli", "alice", "formality", 0.75)
        await store.set_metric("cli", "alice", "preferred_length", 150)

        platform_token = current_platform.set("cli")
        user_token = current_platform_user.set("alice")
        try:
            result = await reset_profile_tool()
            assert "Reset style profile" in result
            assert "2 metrics removed" in result

            metrics = await store.list_metrics("cli", "alice")
            assert len(metrics) == 0
        finally:
            current_platform.reset(platform_token)
            current_platform_user.reset(user_token)

    @pytest.mark.asyncio
    async def test_reset_style_metric_requires_confirmation(self, tools):
        """reset_style_metric requires confirmation."""
        _, _, reset_metric_tool, _ = tools
        assert hasattr(reset_metric_tool, "__hestia_tool__")
        assert reset_metric_tool.__hestia_tool__.requires_confirmation is True

    @pytest.mark.asyncio
    async def test_reset_style_profile_requires_confirmation(self, tools):
        """reset_style_profile requires confirmation."""
        _, _, _, reset_profile_tool = tools
        assert hasattr(reset_profile_tool, "__hestia_tool__")
        assert reset_profile_tool.__hestia_tool__.requires_confirmation is True

    @pytest.mark.asyncio
    async def test_show_style_profile_does_not_require_confirmation(self, tools):
        """show_style_profile does not require confirmation."""
        _, show_tool, _, _ = tools
        assert hasattr(show_tool, "__hestia_tool__")
        assert show_tool.__hestia_tool__.requires_confirmation is False

    @pytest.mark.asyncio
    async def test_tools_have_self_management_capability(self, tools):
        """All style tools have SELF_MANAGEMENT capability."""
        from hestia.tools.capabilities import SELF_MANAGEMENT

        _, show_tool, reset_metric_tool, reset_profile_tool = tools
        for tool_func in [show_tool, reset_metric_tool, reset_profile_tool]:
            assert hasattr(tool_func, "__hestia_tool__")
            assert SELF_MANAGEMENT in tool_func.__hestia_tool__.capabilities
