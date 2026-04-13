"""Unit tests for HestiaConfig."""

from pathlib import Path

import pytest

from hestia.config import DEFAULT_SOUL_MD_PATH, HestiaConfig, IdentityConfig


class TestDefaultConfig:
    """Tests for default configuration values."""

    def test_default_config_has_sensible_values(self):
        """Default config has sensible values for all fields."""
        cfg = HestiaConfig.default()

        # Inference defaults
        assert cfg.inference.base_url == "http://localhost:8001"
        assert cfg.inference.model_name == "Qwen3.5-9B-UD-Q4_K_XL.gguf"
        assert cfg.inference.default_reasoning_budget == 2048
        assert cfg.inference.max_tokens == 1024

        # Slot defaults
        assert cfg.slots.slot_dir == Path("slots")
        assert cfg.slots.pool_size == 4

        # Scheduler defaults
        assert cfg.scheduler.tick_interval_seconds == 5.0

        # Storage defaults
        assert cfg.storage.database_url == "sqlite+aiosqlite:///hestia.db"
        assert cfg.storage.artifacts_dir == Path("artifacts")

        # Top-level defaults
        assert cfg.system_prompt == "You are a helpful assistant."
        assert cfg.max_iterations == 10
        assert cfg.verbose is False

        # Identity defaults to SOUL.md in cwd
        assert cfg.identity.soul_path == DEFAULT_SOUL_MD_PATH
        assert IdentityConfig().soul_path == DEFAULT_SOUL_MD_PATH

    def test_default_factory_creates_new_instances(self):
        """Each call to default() creates fresh instances."""
        cfg1 = HestiaConfig.default()
        cfg2 = HestiaConfig.default()

        # Same values
        assert cfg1.inference.base_url == cfg2.inference.base_url

        # But different objects
        assert cfg1.inference is not cfg2.inference
        assert cfg1.slots is not cfg2.slots

    def test_default_telegram_config(self):
        """Default Telegram config has sensible values."""
        cfg = HestiaConfig.default()
        assert cfg.telegram.bot_token == ""
        assert cfg.telegram.rate_limit_edits_seconds == 1.5
        assert cfg.telegram.http_version == "1.1"
        assert cfg.telegram.allowed_users == []


class TestFromFile:
    """Tests for loading config from Python files."""

    def test_from_file_loads_python_config(self, tmp_path):
        """Can load config from a Python file defining a config variable."""
        config_file = tmp_path / "config.py"
        config_file.write_text("""
from hestia.config import HestiaConfig, InferenceConfig

config = HestiaConfig(
    inference=InferenceConfig(base_url="http://example.com:8001"),
    system_prompt="Custom prompt",
    verbose=True,
)
""")

        cfg = HestiaConfig.from_file(config_file)

        assert cfg.inference.base_url == "http://example.com:8001"
        assert cfg.system_prompt == "Custom prompt"
        assert cfg.verbose is True
        # Other values use defaults
        assert cfg.inference.model_name == "Qwen3.5-9B-UD-Q4_K_XL.gguf"

    def test_from_file_rejects_missing_config_var(self, tmp_path):
        """File without config variable raises TypeError."""
        config_file = tmp_path / "bad_config.py"
        config_file.write_text("""
# No config variable here
x = 1
""")

        with pytest.raises(TypeError, match="Config file must define a `config` variable"):
            HestiaConfig.from_file(config_file)

    def test_from_file_rejects_missing_file(self, tmp_path):
        """Non-existent file raises FileNotFoundError."""
        missing_file = tmp_path / "does_not_exist.py"

        with pytest.raises(FileNotFoundError, match="Config file not found"):
            HestiaConfig.from_file(missing_file)

    def test_from_file_rejects_wrong_type(self, tmp_path):
        """File with config of wrong type raises TypeError."""
        config_file = tmp_path / "wrong_type.py"
        config_file.write_text("""
config = "not a HestiaConfig"
""")

        with pytest.raises(TypeError, match="Config file must define a `config` variable"):
            HestiaConfig.from_file(config_file)
