"""Example Hestia configuration file for Matrix deployment."""

from pathlib import Path

from hestia.config import (
    DEFAULT_SOUL_MD_PATH,
    HestiaConfig,
    IdentityConfig,
    InferenceConfig,
    MatrixConfig,
    SchedulerConfig,
    SlotConfig,
    StorageConfig,
    TrustConfig,
)

config = HestiaConfig(
    inference=InferenceConfig(
        base_url="http://127.0.0.1:8001",
        model_name="your-model-Q4_K_M.gguf",  # Must match the filename of your GGUF model
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
    matrix=MatrixConfig(
        homeserver="https://matrix.org",
        user_id="@hestia-bot:matrix.org",
        access_token="YOUR_ACCESS_TOKEN_HERE",
        allowed_rooms=["!your-room-id:matrix.org"],
        rate_limit_edits_seconds=1.5,
    ),
    identity=IdentityConfig(
        soul_path=Path("/opt/hestia") / DEFAULT_SOUL_MD_PATH.name,
    ),
    trust=TrustConfig.household(),
    system_prompt="You are Hestia, a helpful personal assistant.",
    max_iterations=10,
)
