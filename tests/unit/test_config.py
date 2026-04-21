"""Unit tests for HestiaConfig."""

from pathlib import Path

import pytest

from hestia.config import (
    DEFAULT_SOUL_MD_PATH,
    DiscordVoiceConfig,
    HestiaConfig,
    IdentityConfig,
    InferenceConfig,
    MatrixConfig,
    ReflectionConfig,
    StyleConfig,
    _ConfigFromEnv,
    validate_discord_voice_for_run,
    validate_inference_model_name,
)


class TestDefaultConfig:
    """Tests for default configuration values."""

    def test_default_config_has_sensible_values(self):
        """Default config has sensible values for all fields."""
        cfg = HestiaConfig.default()

        # Inference defaults
        assert cfg.inference.base_url == "http://localhost:8001"
        assert cfg.inference.model_name == ""
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
        assert cfg.discord_voice.enabled is False
        assert cfg.discord_voice.bot_token == ""

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


class TestInferenceModelValidation:
    """H-5: reserved ``dummy`` model name."""

    def test_dummy_requires_allow_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HESTIA_ALLOW_DUMMY_MODEL", raising=False)
        with pytest.raises(ValueError, match="dummy"):
            validate_inference_model_name("dummy")
        monkeypatch.setenv("HESTIA_ALLOW_DUMMY_MODEL", "1")
        validate_inference_model_name("dummy")

    def test_real_model_names_always_ok(self) -> None:
        validate_inference_model_name("my-model-Q4_K_M.gguf")
        validate_inference_model_name("")


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
        assert cfg.inference.model_name == ""

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


class TestMatrixConfigFromEnv:
    """Tests for MatrixConfig.from_env."""

    def test_from_env_uses_defaults_when_empty(self):
        """Loading from empty env yields sensible defaults."""
        cfg = MatrixConfig.from_env(environ={})
        assert cfg.homeserver == "https://matrix.org"
        assert cfg.user_id == ""
        assert cfg.device_id == "hestia-bot"
        assert cfg.access_token == ""
        assert cfg.allowed_rooms == []

    def test_from_env_parses_all_fields(self):
        """All supported env vars are parsed correctly."""
        env = {
            "HESTIA_MATRIX_HOMESERVER": "https://custom.example.com",
            "HESTIA_MATRIX_USER_ID": "@bot:example.com",
            "HESTIA_MATRIX_DEVICE_ID": "device-42",
            "HESTIA_MATRIX_ACCESS_TOKEN": "secret-token",
            "HESTIA_MATRIX_ALLOWED_ROOMS": '["!room1:example.com", "#room2:example.com"]',
        }
        cfg = MatrixConfig.from_env(environ=env)
        assert cfg.homeserver == "https://custom.example.com"
        assert cfg.user_id == "@bot:example.com"
        assert cfg.device_id == "device-42"
        assert cfg.access_token == "secret-token"
        assert cfg.allowed_rooms == ["!room1:example.com", "#room2:example.com"]

    def test_from_env_ignores_empty_allowed_rooms(self):
        """Empty JSON list yields empty allowed rooms."""
        env = {"HESTIA_MATRIX_ALLOWED_ROOMS": "[]"}
        cfg = MatrixConfig.from_env(environ=env)
        assert cfg.allowed_rooms == []


class TestDiscordVoiceConfigFromEnv:
    """Tests for DiscordVoiceConfig.from_env."""

    def test_from_env_defaults_when_empty(self):
        cfg = DiscordVoiceConfig.from_env(environ={})
        assert cfg.enabled is False
        assert cfg.bot_token == ""
        assert cfg.guild_id == 0
        assert cfg.voice_channel_id == 0
        assert cfg.text_channel_id is None
        assert cfg.allowed_speaker_ids == ()

    def test_from_env_canonical_keys(self):
        env = {
            "HESTIA_DISCORD_TOKEN": "bot-secret",
            "HESTIA_DISCORD_GUILD_ID": "111",
            "HESTIA_DISCORD_VOICE_CHANNEL_ID": "222",
            "HESTIA_DISCORD_TEXT_CHANNEL_ID": "333",
            "HESTIA_DISCORD_ALLOWED_USER_IDS": "[444, 555]",
            "HESTIA_DISCORD_VOICE_ENABLED": "1",
        }
        cfg = DiscordVoiceConfig.from_env(environ=env)
        assert cfg.enabled is True
        assert cfg.bot_token == "bot-secret"
        assert cfg.guild_id == 111
        assert cfg.voice_channel_id == 222
        assert cfg.text_channel_id == 333
        assert cfg.allowed_speaker_ids == (444, 555)

    def test_from_env_legacy_aliases(self):
        env = {
            "HESTIA_DISCORD_TOKEN": "t",
            "DISCORD_GUILD": "9",
            "DISCORD_VOICE_CHANNEL": "8",
            "DISCORD_TEXT_CHANNEL": "7",
            "ALLOWED_DISCORD_USERS": "[1, 2]",
        }
        with pytest.warns(DeprecationWarning):
            cfg = DiscordVoiceConfig.from_env(environ=env)
        assert cfg.enabled is False
        assert cfg.guild_id == 9
        assert cfg.voice_channel_id == 8
        assert cfg.text_channel_id == 7
        assert cfg.allowed_speaker_ids == (1, 2)

    def test_from_env_canonical_overrides_legacy(self):
        env = {
            "HESTIA_DISCORD_GUILD_ID": "100",
            "DISCORD_GUILD": "999",
            "HESTIA_DISCORD_VOICE_CHANNEL_ID": "200",
            "DISCORD_VOICE_CHANNEL": "888",
        }
        cfg = DiscordVoiceConfig.from_env(environ=env)
        assert cfg.guild_id == 100
        assert cfg.voice_channel_id == 200

    def test_from_env_enabled_false_explicit(self):
        env = {
            "HESTIA_DISCORD_VOICE_ENABLED": "0",
            "HESTIA_DISCORD_TOKEN": "x",
        }
        cfg = DiscordVoiceConfig.from_env(environ=env)
        assert cfg.enabled is False

    def test_from_env_invalid_numeric_ids_raise(self):
        """Invalid numeric env values now raise ValueError with a clear message."""
        env = {"HESTIA_DISCORD_GUILD_ID": "not-a-number"}
        with pytest.raises(ValueError, match="HESTIA_DISCORD_GUILD_ID"):
            DiscordVoiceConfig.from_env(environ=env)

    def test_from_env_empty_text_channel_becomes_none(self):
        env = {
            "HESTIA_DISCORD_VOICE_CHANNEL_ID": "",
            "HESTIA_DISCORD_TEXT_CHANNEL_ID": "",
        }
        cfg = DiscordVoiceConfig.from_env(environ=env)
        assert cfg.voice_channel_id == 0  # default
        assert cfg.text_channel_id is None  # int | None, empty → None


class TestConfigFromEnvMixin:
    """Tests for the shared _ConfigFromEnv mixin."""

    def test_happy_path_str(self):
        cfg = MatrixConfig.from_env(environ={"HESTIA_MATRIX_HOMESERVER": "https://x.org"})
        assert cfg.homeserver == "https://x.org"

    def test_happy_path_int(self):
        cfg = MatrixConfig.from_env(environ={"HESTIA_MATRIX_SYNC_TIMEOUT_MS": "42"})
        assert cfg.sync_timeout_ms == 42

    def test_happy_path_float(self):
        cfg = MatrixConfig.from_env(environ={"HESTIA_MATRIX_RATE_LIMIT_EDITS_SECONDS": "2.5"})
        assert cfg.rate_limit_edits_seconds == 2.5

    def test_happy_path_bool(self):
        for val in ("1", "true", "yes", "on"):
            cfg = DiscordVoiceConfig.from_env(environ={"HESTIA_DISCORD_VOICE_ENABLED": val})
            assert cfg.enabled is True, val
        for val in ("0", "false", "no", "off"):
            cfg = DiscordVoiceConfig.from_env(environ={"HESTIA_DISCORD_VOICE_ENABLED": val})
            assert cfg.enabled is False, val

    def test_happy_path_path(self):
        cfg = IdentityConfig.from_env(environ={"HESTIA_IDENTITY_SOUL_PATH": "/tmp/SOUL.md"})
        assert cfg.soul_path == Path("/tmp/SOUL.md")

    def test_happy_path_list_str(self):
        cfg = MatrixConfig.from_env(
            environ={"HESTIA_MATRIX_ALLOWED_ROOMS": '["a", "b"]'},
        )
        assert cfg.allowed_rooms == ["a", "b"]

    def test_malformed_json_raises(self):
        env = {"HESTIA_MATRIX_ALLOWED_ROOMS": "not-json"}
        with pytest.raises(ValueError, match="HESTIA_MATRIX_ALLOWED_ROOMS"):
            MatrixConfig.from_env(environ=env)

    def test_unknown_fields_ignored(self):
        """Env vars that do not map to known fields are silently ignored."""
        cfg = MatrixConfig.from_env(environ={"HESTIA_MATRIX_UNKNOWN_FIELD": "42"})
        assert cfg.homeserver == "https://matrix.org"  # default unchanged

    def test_legacy_alias_emits_warning(self):
        env = {"DISCORD_GUILD": "123"}
        with pytest.warns(DeprecationWarning, match="DISCORD_GUILD"):
            cfg = DiscordVoiceConfig.from_env(environ=env)
        assert cfg.guild_id == 123


class TestConfigValidation:
    """Tests for config validation hardening."""

    def test_negative_identity_max_tokens_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            IdentityConfig(max_tokens=-1)

    def test_negative_inference_max_tokens_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            InferenceConfig(max_tokens=-1)

    def test_unparseable_style_cron_rejected(self):
        with pytest.raises(ValueError, match="cron"):
            StyleConfig(cron="not-a-cron")

    def test_unparseable_reflection_cron_rejected(self):
        with pytest.raises(ValueError, match="cron"):
            ReflectionConfig(cron="invalid")

    def test_from_file_rejects_negative_max_tokens(self, tmp_path):
        config_file = tmp_path / "bad.py"
        config_file.write_text("""
from hestia.config import HestiaConfig, InferenceConfig
config = HestiaConfig(inference=InferenceConfig(max_tokens=-5))
""")
        with pytest.raises(ValueError, match="non-negative"):
            HestiaConfig.from_file(config_file)

    def test_from_file_rejects_bad_cron(self, tmp_path):
        config_file = tmp_path / "bad.py"
        config_file.write_text("""
from hestia.config import HestiaConfig, StyleConfig
config = HestiaConfig(style=StyleConfig(cron="bad"))
""")
        with pytest.raises(ValueError, match="cron"):
            HestiaConfig.from_file(config_file)


class TestValidateDiscordVoiceForRun:
    """Tests for validate_discord_voice_for_run."""

    def test_disabled_is_noop(self) -> None:
        validate_discord_voice_for_run(DiscordVoiceConfig(enabled=False))

    def test_enabled_requires_token_and_ids(self) -> None:
        with pytest.raises(ValueError, match="bot_token"):
            validate_discord_voice_for_run(
                DiscordVoiceConfig(enabled=True, guild_id=1, voice_channel_id=1)
            )
        with pytest.raises(ValueError, match="guild_id"):
            validate_discord_voice_for_run(
                DiscordVoiceConfig(
                    enabled=True, bot_token="x", guild_id=0, voice_channel_id=1
                )
            )
        validate_discord_voice_for_run(
            DiscordVoiceConfig(enabled=True, bot_token="x", guild_id=1, voice_channel_id=2)
        )


class TestInferenceConfigDummyRejection:
    """H-5: reject the literal placeholder 'dummy' at config-load."""

    def test_dummy_model_name_rejected_by_default(self, monkeypatch):
        """Explicit model_name='dummy' raises ValueError at construct-time."""
        monkeypatch.delenv("HESTIA_ALLOW_DUMMY_MODEL", raising=False)
        with pytest.raises(ValueError, match="model_name == 'dummy' is rejected"):
            InferenceConfig(model_name="dummy")

    def test_dummy_model_name_allowed_with_env_override(self, monkeypatch):
        """HESTIA_ALLOW_DUMMY_MODEL=1 lets CI/test paths keep the placeholder."""
        monkeypatch.setenv("HESTIA_ALLOW_DUMMY_MODEL", "1")
        cfg = InferenceConfig(model_name="dummy")
        assert cfg.model_name == "dummy"

    def test_empty_model_name_still_allowed(self, monkeypatch):
        """Empty model_name is not 'dummy' — CLI/setup paths rely on this."""
        monkeypatch.delenv("HESTIA_ALLOW_DUMMY_MODEL", raising=False)
        cfg = InferenceConfig()
        assert cfg.model_name == ""

    def test_real_model_name_unaffected(self, monkeypatch):
        """Any model name other than the literal 'dummy' passes through."""
        monkeypatch.delenv("HESTIA_ALLOW_DUMMY_MODEL", raising=False)
        cfg = InferenceConfig(model_name="qwen2.5-7b-instruct-q4_k_m.gguf")
        assert cfg.model_name == "qwen2.5-7b-instruct-q4_k_m.gguf"
