"""Unit tests for TrustConfig presets."""

from hestia.config import HestiaConfig, TrustConfig


class TestTrustConfigPresets:
    """Tests for TrustConfig preset profiles."""

    def test_default_matches_paranoid(self):
        """Default TrustConfig() must match paranoid preset."""
        default = TrustConfig()
        paranoid = TrustConfig.paranoid()
        assert default.auto_approve_tools == paranoid.auto_approve_tools == []
        assert default.scheduler_shell_exec is paranoid.scheduler_shell_exec is False
        assert default.subagent_shell_exec is paranoid.subagent_shell_exec is False
        assert default.subagent_write_local is paranoid.subagent_write_local is False

    def test_household_preset(self):
        """Household preset auto-approves terminal and write_file."""
        household = TrustConfig.household()
        assert household.auto_approve_tools == ["terminal", "write_file"]
        assert household.scheduler_shell_exec is True
        assert household.subagent_shell_exec is True
        assert household.subagent_write_local is True

    def test_developer_preset(self):
        """Developer preset has wildcard and all flags True."""
        developer = TrustConfig.developer()
        assert developer.auto_approve_tools == ["*"]
        assert developer.scheduler_shell_exec is True
        assert developer.subagent_shell_exec is True
        assert developer.subagent_write_local is True

    def test_prompt_on_mobile_preset(self):
        """prompt_on_mobile auto-approves nothing but keeps household flags."""
        mobile = TrustConfig.prompt_on_mobile()
        assert mobile.auto_approve_tools == []
        assert mobile.scheduler_shell_exec is True
        assert mobile.subagent_shell_exec is True
        assert mobile.subagent_write_local is True


class TestHestiaConfigForTrust:
    """Tests for HestiaConfig.for_trust mapping."""

    def test_paranoid_disables_handoff_and_compression(self):
        """paranoid() implies handoff=False, compression=False."""
        cfg = HestiaConfig.for_trust(TrustConfig.paranoid())
        assert cfg.handoff.enabled is False
        assert cfg.compression.enabled is False

    def test_household_enables_handoff_and_compression(self):
        """household() implies handoff=True, compression=True."""
        cfg = HestiaConfig.for_trust(TrustConfig.household())
        assert cfg.handoff.enabled is True
        assert cfg.compression.enabled is True

    def test_developer_enables_handoff_and_compression(self):
        """developer() implies handoff=True, compression=True."""
        cfg = HestiaConfig.for_trust(TrustConfig.developer())
        assert cfg.handoff.enabled is True
        assert cfg.compression.enabled is True

    def test_default_is_paranoid(self):
        """Default HestiaConfig matches paranoid preset."""
        default = HestiaConfig.default()
        assert default.handoff.enabled is False
        assert default.compression.enabled is False
