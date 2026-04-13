"""Example Hestia configuration file for Telegram deployment."""

from pathlib import Path

from hestia.config import (
    DEFAULT_SOUL_MD_PATH,
    HestiaConfig,
    IdentityConfig,
    InferenceConfig,
    SlotConfig,
    SchedulerConfig,
    StorageConfig,
    TelegramConfig,
)

config = HestiaConfig(
    inference=InferenceConfig(
        base_url="http://127.0.0.1:8001",
        model_name="Qwen3.5-9B-UD-Q4_K_XL.gguf",
        default_reasoning_budget=2048,
        max_tokens=1024,
    ),
    slots=SlotConfig(
        slot_dir=Path("/opt/hestia/slots"),
        pool_size=4,
    ),
    scheduler=SchedulerConfig(
        tick_interval_seconds=5.0,
    ),
    storage=StorageConfig(
        database_url="sqlite+aiosqlite:////opt/hestia/data/hestia.db",
        artifacts_dir=Path("/opt/hestia/data/artifacts"),
    ),
    telegram=TelegramConfig(
        bot_token="YOUR_BOT_TOKEN_HERE",
        allowed_users=["YOUR_TELEGRAM_USER_ID"],
        rate_limit_edits_seconds=1.5,
    ),
    identity=IdentityConfig(
        soul_path=Path("/opt/hestia") / DEFAULT_SOUL_MD_PATH.name,
    ),
    system_prompt="You are Hestia, a helpful personal assistant.",
    max_iterations=10,
)
