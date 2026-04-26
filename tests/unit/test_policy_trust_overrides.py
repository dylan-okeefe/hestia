"""Unit tests for per-user trust overrides in DefaultPolicyEngine."""

import pytest

from hestia.config import StorageConfig, TrustConfig
from hestia.core.types import Session, SessionState, SessionTemperature
from hestia.policy.default import DefaultPolicyEngine


@pytest.fixture
def sample_session():
    """Sample session fixture."""
    from datetime import datetime

    return Session(
        id="test_session",
        platform="telegram",
        platform_user="123456789",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )


@pytest.fixture
def guest_session():
    """Guest session fixture."""
    from datetime import datetime

    return Session(
        id="guest_session",
        platform="telegram",
        platform_user="987654321",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )


class TestTrustForResolution:
    """Tests for _trust_for session-based resolution."""

    def test_default_trust_when_no_override(self, sample_session):
        """No override returns the default trust profile."""
        default = TrustConfig.paranoid()
        policy = DefaultPolicyEngine(trust=default)
        resolved = policy._trust_for(sample_session)
        assert resolved is default

    def test_override_for_matching_identity(self, sample_session):
        """Matching platform:platform_user returns the override."""
        owner_trust = TrustConfig.developer()
        policy = DefaultPolicyEngine(
            trust=TrustConfig.paranoid(),
            trust_overrides={"telegram:123456789": owner_trust},
        )
        resolved = policy._trust_for(sample_session)
        assert resolved is owner_trust

    def test_fallback_for_non_matching_identity(self, sample_session, guest_session):
        """Non-matching identity falls back to default trust."""
        default = TrustConfig.paranoid()
        owner_trust = TrustConfig.developer()
        policy = DefaultPolicyEngine(
            trust=default,
            trust_overrides={"telegram:123456789": owner_trust},
        )
        resolved = policy._trust_for(guest_session)
        assert resolved is default

    def test_missing_platform_user_fallback(self, sample_session, caplog):
        """Missing platform_user falls back to default with warning."""
        from dataclasses import replace

        default = TrustConfig.paranoid()
        policy = DefaultPolicyEngine(trust=default)
        bad_session = replace(sample_session, platform_user="")
        with caplog.at_level("WARNING"):
            resolved = policy._trust_for(bad_session)
        assert resolved is default
        assert "missing identity" in caplog.text

    def test_missing_platform_fallback(self, sample_session, caplog):
        """Missing platform falls back to default with warning."""
        from dataclasses import replace

        default = TrustConfig.paranoid()
        policy = DefaultPolicyEngine(trust=default)
        bad_session = replace(sample_session, platform="")
        with caplog.at_level("WARNING"):
            resolved = policy._trust_for(bad_session)
        assert resolved is default
        assert "missing identity" in caplog.text


class TestAutoApproveOverrides:
    """Tests for auto_approve with per-user trust overrides."""

    def test_owner_auto_approves_with_override(self, sample_session):
        """Owner with developer override gets auto-approval."""
        policy = DefaultPolicyEngine(
            trust=TrustConfig.paranoid(),
            trust_overrides={"telegram:123456789": TrustConfig.developer()},
        )
        assert policy.auto_approve("any_tool", sample_session)

    def test_guest_denied_without_override(self, sample_session, guest_session):
        """Guest without override is denied under paranoid default."""
        policy = DefaultPolicyEngine(
            trust=TrustConfig.paranoid(),
            trust_overrides={"telegram:123456789": TrustConfig.developer()},
        )
        assert not policy.auto_approve("any_tool", guest_session)

    def test_guest_approved_with_own_override(self, guest_session):
        """Guest with their own override is approved."""
        policy = DefaultPolicyEngine(
            trust=TrustConfig.paranoid(),
            trust_overrides={"telegram:987654321": TrustConfig.household()},
        )
        assert policy.auto_approve("terminal", guest_session)
        assert policy.auto_approve("write_file", guest_session)
        assert not policy.auto_approve("other_tool", guest_session)


class TestFilterToolsOverrides:
    """Tests for filter_tools with per-user trust overrides."""

    def test_scheduler_tick_uses_creator_override(self, sample_session, tmp_path):
        """Scheduler tick resolves trust against creator's override, not default."""
        from hestia.artifacts.store import ArtifactStore
        from hestia.runtime_context import scheduler_tick_active
        from hestia.tools.builtin import current_time, make_terminal_tool
        terminal = make_terminal_tool()
        from hestia.tools.registry import ToolRegistry

        # Owner gets household trust (allows scheduler shell)
        owner_trust = TrustConfig.household()
        policy = DefaultPolicyEngine(
            trust=TrustConfig.paranoid(),
            trust_overrides={"telegram:123456789": owner_trust},
        )
        reg = ToolRegistry(ArtifactStore(tmp_path / "art"))
        reg.register(current_time)
        reg.register(terminal)
        names = reg.list_names()

        token = scheduler_tick_active.set(True)
        try:
            filtered = policy.filter_tools(sample_session, names, reg)
        finally:
            scheduler_tick_active.reset(token)

        # Under household override, terminal should be allowed in scheduler
        assert "terminal" in filtered
        assert "current_time" in filtered

    def test_guest_scheduler_tick_uses_default(self, guest_session, tmp_path):
        """Guest without override gets default paranoid trust in scheduler tick."""
        from hestia.artifacts.store import ArtifactStore
        from hestia.runtime_context import scheduler_tick_active
        from hestia.tools.builtin import current_time, make_terminal_tool
        terminal = make_terminal_tool()
        from hestia.tools.registry import ToolRegistry

        policy = DefaultPolicyEngine(trust=TrustConfig.paranoid())
        reg = ToolRegistry(ArtifactStore(tmp_path / "art"))
        reg.register(current_time)
        reg.register(terminal)
        names = reg.list_names()

        token = scheduler_tick_active.set(True)
        try:
            filtered = policy.filter_tools(guest_session, names, reg)
        finally:
            scheduler_tick_active.reset(token)

        assert "terminal" not in filtered
        assert "current_time" in filtered

    def test_subagent_uses_override_when_key_matches(self, tmp_path):
        """Subagent session with a matching override key uses the override."""
        from datetime import datetime

        from hestia.artifacts.store import ArtifactStore
        from hestia.tools.builtin import current_time, make_write_file_tool, make_terminal_tool
        terminal = make_terminal_tool()
        from hestia.tools.registry import ToolRegistry

        sub = Session(
            id="sub_session",
            platform="subagent",
            platform_user="subagent_abc123",
            started_at=datetime.now(),
            last_active_at=datetime.now(),
            slot_id=None,
            slot_saved_path=None,
            state=SessionState.ACTIVE,
            temperature=SessionTemperature.COLD,
        )
        # Override for this specific subagent identity
        policy = DefaultPolicyEngine(
            trust=TrustConfig.household(),
            trust_overrides={"subagent:subagent_abc123": TrustConfig.paranoid()},
        )
        reg = ToolRegistry(ArtifactStore(tmp_path / "art"))
        reg.register(current_time)
        reg.register(terminal)
        reg.register(make_write_file_tool(StorageConfig(allowed_roots=[str(tmp_path)])))
        names = reg.list_names()

        filtered = policy.filter_tools(sub, names, reg)
        assert "terminal" not in filtered
        assert "write_file" not in filtered
        assert "current_time" in filtered
