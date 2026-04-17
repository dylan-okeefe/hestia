"""Unit tests for CompressionConfig."""

from hestia.config import CompressionConfig


class TestCompressionConfigDefaults:
    """Tests for CompressionConfig default values."""

    def test_defaults(self):
        """Default CompressionConfig is disabled with sensible limits."""
        cfg = CompressionConfig()
        assert cfg.enabled is False
        assert cfg.max_chars == 400

    def test_custom_values(self):
        """CompressionConfig accepts overrides."""
        cfg = CompressionConfig(enabled=True, max_chars=300)
        assert cfg.enabled is True
        assert cfg.max_chars == 300
