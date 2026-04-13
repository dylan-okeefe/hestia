"""Typed configuration for Hestia."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class InferenceConfig:
    """Configuration for the llama.cpp inference server."""

    base_url: str = "http://localhost:8001"
    model_name: str = "Qwen3.5-9B-UD-Q4_K_XL.gguf"
    default_reasoning_budget: int = 2048
    max_tokens: int = 1024


@dataclass
class SlotConfig:
    """Configuration for the SlotManager."""

    slot_dir: Path = field(default_factory=lambda: Path("slots"))
    pool_size: int = 4


@dataclass
class SchedulerConfig:
    """Configuration for the Scheduler."""

    tick_interval_seconds: float = 5.0


@dataclass
class StorageConfig:
    """Configuration for persistence and artifact storage."""

    database_url: str = "sqlite+aiosqlite:///hestia.db"
    artifacts_dir: Path = field(default_factory=lambda: Path("artifacts"))
    allowed_roots: list[str] = field(default_factory=lambda: ["."])


@dataclass
class TelegramConfig:
    """Configuration for the Telegram adapter."""

    bot_token: str = ""
    allowed_users: list[str] = field(default_factory=list)
    rate_limit_edits_seconds: float = 1.5
    http_version: str = "1.1"  # Force HTTP/1.1 for Telegram API stability
    fallback_ips: list[str] = field(
        default_factory=lambda: [
            "149.154.167.220",  # api.telegram.org primary
        ]
    )
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 30.0
    long_poll_timeout_seconds: float = 30.0


@dataclass
class MatrixConfig:
    """Configuration for the Matrix adapter.

    Security: allowed_rooms is a whitelist. Empty list denies all inbound.
    Session mapping: one Matrix room -> one Hestia session (room ID as platform_user).
    """

    homeserver: str = "https://matrix.org"
    user_id: str = ""  # Bot MXID e.g., @hestia-bot:matrix.org
    device_id: str = "hestia-bot"
    access_token: str = ""  # From login or admin token
    allowed_rooms: list[str] = field(default_factory=list)  # Room IDs or aliases
    rate_limit_edits_seconds: float = 1.5
    sync_timeout_ms: int = 30000  # Long-poll timeout for /sync


@dataclass
class HestiaConfig:
    """Top-level Hestia configuration.

    CLI options override values set here. Config files are loaded
    with HestiaConfig.from_file() and merged with CLI overrides.
    """

    inference: InferenceConfig = field(default_factory=InferenceConfig)
    slots: SlotConfig = field(default_factory=SlotConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    matrix: MatrixConfig = field(default_factory=MatrixConfig)
    system_prompt: str = "You are a helpful assistant."
    max_iterations: int = 10
    verbose: bool = False

    @classmethod
    def from_file(cls, path: Path) -> HestiaConfig:
        """Load config from a Python file.

        The file must define a `config` variable of type HestiaConfig.
        """
        import importlib.util

        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        spec = importlib.util.spec_from_file_location("hestia_config", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load config file: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        config = getattr(module, "config", None)
        if not isinstance(config, HestiaConfig):
            raise TypeError(
                f"Config file must define a `config` variable of type HestiaConfig, "
                f"got {type(config).__name__}"
            )
        return config

    @classmethod
    def default(cls) -> HestiaConfig:
        return cls()
