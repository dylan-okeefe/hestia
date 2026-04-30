"""Example Hestia configuration file for CLI-only deployment.

No platform integrations (Telegram, Matrix, Email). Use this for local
development, testing, or when you only interact via the terminal.
"""

from pathlib import Path

from hestia.config import (
    DEFAULT_SOUL_MD_PATH,
    HestiaConfig,
    IdentityConfig,
    InferenceConfig,
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
        slot_dir=Path("slots"),
        pool_size=4,
    ),
    storage=StorageConfig(
        database_url="sqlite+aiosqlite:///hestia.db",
        artifacts_dir=Path("artifacts"),
        allowed_roots=["."],
    ),
    identity=IdentityConfig(
        soul_path=Path.cwd() / DEFAULT_SOUL_MD_PATH.name,
    ),
    trust=TrustConfig.developer(),  # Relaxed for local CLI use
    system_prompt="You are Hestia, a helpful personal assistant.",
    max_iterations=10,
)
