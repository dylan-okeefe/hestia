"""Unit tests for self-management capability trust gating."""

from __future__ import annotations

import pytest

from hestia.config import TrustConfig
from hestia.core.types import Session, SessionState, SessionTemperature
from hestia.policy.default import DefaultPolicyEngine
from hestia.tools.capabilities import SELF_MANAGEMENT
from hestia.tools.metadata import tool


def _make_session(platform: str = "cli") -> Session:
    from datetime import datetime

    return Session(
        id="test-session",
        platform=platform,
        platform_user="user",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.HOT,
    )


@pytest.fixture
def sample_session():
    return _make_session()


class TestSelfManagementFiltering:
    """Tests for self-management tool filtering by trust level."""

    def test_paranoid_blocks_self_management(self, sample_session, tmp_path):
        """Paranoid trust blocks self-management tools."""
        from hestia.artifacts.store import ArtifactStore
        from hestia.tools.registry import ToolRegistry

        policy = DefaultPolicyEngine(trust=TrustConfig.paranoid())
        reg = ToolRegistry(ArtifactStore(tmp_path / "art"))

        @tool(
            name="list_proposals",
            public_description="List proposals",
            capabilities=[SELF_MANAGEMENT],
        )
        async def _list_proposals() -> str:
            return "ok"

        reg.register(_list_proposals)
        names = reg.list_names()
        filtered = policy.filter_tools(sample_session, names, reg)
        assert "list_proposals" not in filtered

    def test_household_allows_self_management(self, sample_session, tmp_path):
        """Household trust allows self-management tools."""
        from hestia.artifacts.store import ArtifactStore
        from hestia.tools.registry import ToolRegistry

        policy = DefaultPolicyEngine(trust=TrustConfig.household())
        reg = ToolRegistry(ArtifactStore(tmp_path / "art"))

        @tool(
            name="list_proposals",
            public_description="List proposals",
            capabilities=[SELF_MANAGEMENT],
        )
        async def _list_proposals() -> str:
            return "ok"

        reg.register(_list_proposals)
        names = reg.list_names()
        filtered = policy.filter_tools(sample_session, names, reg)
        assert "list_proposals" in filtered

    def test_developer_allows_self_management(self, sample_session, tmp_path):
        """Developer trust allows self-management tools."""
        from hestia.artifacts.store import ArtifactStore
        from hestia.tools.registry import ToolRegistry

        policy = DefaultPolicyEngine(trust=TrustConfig.developer())
        reg = ToolRegistry(ArtifactStore(tmp_path / "art"))

        @tool(
            name="list_proposals",
            public_description="List proposals",
            capabilities=[SELF_MANAGEMENT],
        )
        async def _list_proposals() -> str:
            return "ok"

        reg.register(_list_proposals)
        names = reg.list_names()
        filtered = policy.filter_tools(sample_session, names, reg)
        assert "list_proposals" in filtered

    def test_prompt_on_mobile_blocks_self_management(self, sample_session, tmp_path):
        """Prompt-on-mobile trust blocks self-management tools."""
        from hestia.artifacts.store import ArtifactStore
        from hestia.tools.registry import ToolRegistry

        policy = DefaultPolicyEngine(trust=TrustConfig.prompt_on_mobile())
        reg = ToolRegistry(ArtifactStore(tmp_path / "art"))

        @tool(
            name="list_proposals",
            public_description="List proposals",
            capabilities=[SELF_MANAGEMENT],
        )
        async def _list_proposals() -> str:
            return "ok"

        reg.register(_list_proposals)
        names = reg.list_names()
        filtered = policy.filter_tools(sample_session, names, reg)
        assert "list_proposals" not in filtered

    def test_non_self_management_tools_always_allowed(self, sample_session, tmp_path):
        """Tools without self-management capability are never filtered by trust."""
        from hestia.artifacts.store import ArtifactStore
        from hestia.tools.registry import ToolRegistry

        policy = DefaultPolicyEngine(trust=TrustConfig.paranoid())
        reg = ToolRegistry(ArtifactStore(tmp_path / "art"))

        @tool(
            name="current_time",
            public_description="Get current time",
            capabilities=[],
        )
        async def _current_time() -> str:
            return "ok"

        reg.register(_current_time)
        names = reg.list_names()
        filtered = policy.filter_tools(sample_session, names, reg)
        assert "current_time" in filtered

    def test_subagent_blocks_self_management_when_paranoid(self, sample_session, tmp_path):
        """Subagent sessions block self-management under paranoid trust."""
        from dataclasses import replace

        from hestia.artifacts.store import ArtifactStore
        from hestia.tools.registry import ToolRegistry

        policy = DefaultPolicyEngine(trust=TrustConfig.paranoid())
        reg = ToolRegistry(ArtifactStore(tmp_path / "art"))

        @tool(
            name="list_proposals",
            public_description="List proposals",
            capabilities=[SELF_MANAGEMENT],
        )
        async def _list_proposals() -> str:
            return "ok"

        reg.register(_list_proposals)
        names = reg.list_names()
        sub = replace(sample_session, platform="subagent")
        filtered = policy.filter_tools(sub, names, reg)
        assert "list_proposals" not in filtered

    def test_subagent_allows_self_management_when_household(self, sample_session, tmp_path):
        """Subagent sessions allow self-management under household trust."""
        from dataclasses import replace

        from hestia.artifacts.store import ArtifactStore
        from hestia.tools.registry import ToolRegistry

        policy = DefaultPolicyEngine(trust=TrustConfig.household())
        reg = ToolRegistry(ArtifactStore(tmp_path / "art"))

        @tool(
            name="list_proposals",
            public_description="List proposals",
            capabilities=[SELF_MANAGEMENT],
        )
        async def _list_proposals() -> str:
            return "ok"

        reg.register(_list_proposals)
        names = reg.list_names()
        sub = replace(sample_session, platform="subagent")
        filtered = policy.filter_tools(sub, names, reg)
        assert "list_proposals" in filtered

    def test_partial_trust_config(self, sample_session, tmp_path):
        """Custom trust config can toggle self_management independently."""
        from hestia.artifacts.store import ArtifactStore
        from hestia.tools.registry import ToolRegistry

        trust = TrustConfig(self_management=True)
        policy = DefaultPolicyEngine(trust=trust)
        reg = ToolRegistry(ArtifactStore(tmp_path / "art"))

        @tool(
            name="list_proposals",
            public_description="List proposals",
            capabilities=[SELF_MANAGEMENT],
        )
        async def _list_proposals() -> str:
            return "ok"

        reg.register(_list_proposals)
        names = reg.list_names()
        filtered = policy.filter_tools(sample_session, names, reg)
        assert "list_proposals" in filtered

    def test_is_paranoid_considers_self_management(self):
        """is_paranoid returns False when self_management is enabled."""
        trust = TrustConfig()
        assert trust.is_paranoid() is True

        trust_self_mgmt = TrustConfig(self_management=True)
        assert trust_self_mgmt.is_paranoid() is False
