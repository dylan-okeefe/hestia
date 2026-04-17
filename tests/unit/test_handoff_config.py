"""Unit tests for HandoffConfig."""

from hestia.config import HandoffConfig


class TestHandoffConfigDefaults:
    """Tests for HandoffConfig default values."""

    def test_defaults(self):
        """Default HandoffConfig is disabled with sensible limits."""
        cfg = HandoffConfig()
        assert cfg.enabled is False
        assert cfg.min_messages == 4
        assert cfg.max_chars == 350

    def test_custom_values(self):
        """HandoffConfig accepts overrides."""
        cfg = HandoffConfig(enabled=True, min_messages=2, max_chars=200)
        assert cfg.enabled is True
        assert cfg.min_messages == 2
        assert cfg.max_chars == 200
