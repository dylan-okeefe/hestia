"""Example runtime config for a personal Hestia worktree.

Copy this file to ``config.runtime.py`` and adjust paths, model name, and any
platform credentials. This example uses the safe public posture decided in
C1/C3: web binds to the loopback interface, dashboard auth is enabled, and the
trust preset does not use a wildcard auto-approve.
"""

from pathlib import Path

from hestia.config import (
    HestiaConfig,
    IdentityConfig,
    InferenceConfig,
    SlotConfig,
    StorageConfig,
    TrustConfig,
    WebConfig,
)

_ROOT = Path("/path/to/hestia-runtime-data")
_DB_PATH = _ROOT / "hestia.db"

config = HestiaConfig(
    inference=InferenceConfig(
        base_url="http://127.0.0.1:8001",
        model_name="your-model-Q4_K_M.gguf",
        context_length=8192,
        default_reasoning_budget=2048,
        max_tokens=1024,
        stream=True,
    ),
    slots=SlotConfig(
        slot_dir=_ROOT / "slots",
        pool_size=4,
    ),
    storage=StorageConfig(
        database_url=f"sqlite+aiosqlite:///{_DB_PATH}",
        artifacts_dir=_ROOT / "artifacts",
        allowed_roots=[str(_ROOT)],
    ),
    identity=IdentityConfig(
        soul_path=_ROOT / "SOUL.md",
        compiled_cache_path=_ROOT / "compiled_identity.txt",
    ),
    # Safe posture: loopback-only, auth enabled, no wildcard auto-approve.
    web=WebConfig(
        enabled=True,
        host="127.0.0.1",
        port=8765,
        auth_enabled=True,
        allow_insecure=False,
    ),
    trust=TrustConfig.household(),
)
