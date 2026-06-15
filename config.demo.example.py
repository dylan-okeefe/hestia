"""Demo/screenshot config for the ~/Hestia dev worktree.

Copy this file to ``config.demo.py`` (gitignored) and adjust the inference URL
if your local llama-server is not on ``http://127.0.0.1:8001``. Context Lab
preview needs a running llama-server for token counting; the rest of the web UI
does not.

This config is intentionally web-only: Telegram, Matrix, email, and voice are
left at their empty defaults so ``hestia serve`` does not start any personal
platform adapters. The demo instance binds ``127.0.0.1:8766`` so it can run at
the same time as the personal ``~/Hestia-runtime`` instance on port 8765.

All data lives under ``./demo-data/`` and is also gitignored.
"""

from pathlib import Path

from hestia.config import (
    BrowserConfig,
    HestiaConfig,
    IdentityConfig,
    InferenceConfig,
    SlotConfig,
    StorageConfig,
    WebConfig,
)

_ROOT = Path(__file__).resolve().parent / "demo-data"

config = HestiaConfig(
    inference=InferenceConfig(
        # Point at your local llama-server. Tokenization is read-only;
        # no personal data is sent to the inference server.
        base_url="http://127.0.0.1:8001",
        model_name="your-model-Q4_K_M.gguf",
        default_reasoning_budget=2048,
        max_tokens=1024,
    ),
    slots=SlotConfig(
        slot_dir=_ROOT / "slots",
        pool_size=1,
    ),
    storage=StorageConfig(
        database_url=f"sqlite+aiosqlite:///{_ROOT / 'hestia.db'}",
        artifacts_dir=_ROOT / "artifacts",
        allowed_roots=[str(_ROOT)],
    ),
    identity=IdentityConfig(
        soul_path=_ROOT / "SOUL.md",
        compiled_cache_path=_ROOT / "compiled_identity.txt",
        max_tokens=300,
        recompile_on_change=True,
        capabilities_prefix_enabled=True,
    ),
    browser=BrowserConfig(
        enabled=False,
        session_dir=_ROOT / "browser-sessions",
        headless=True,
    ),
    # Telegram, Matrix, email, and voice are disabled by their empty defaults.
    web=WebConfig(
        enabled=True,
        auth_enabled=True,
        # debug_login is only true for this local demo config; it is NOT added
        # to the product config schema or UI. It lets the seed script mint a
        # bearer token for the mock admin without a 2FA chat adapter.
        debug_login=True,
        host="127.0.0.1",
        port=8766,
        session_lifetime_hours=24,
    ),
    system_prompt=(
        "You are Hestia, a helpful personal assistant.\n\n"
        "This is a local demo instance used for screenshots. "
        "All data is synthetic."
    ),
    max_iterations=5,
)
