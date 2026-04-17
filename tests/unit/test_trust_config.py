"""Unit tests for TrustConfig presets."""

from hestia.config import TrustConfig


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
