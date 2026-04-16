# Runtime and feature worktree testing

How to keep a stable `~/Hestia-runtime` tree while developing and testing feature branches.

---

## Why use worktrees

`~/Hestia-runtime` is the stable, always-on deployment (systemd services, live Telegram/Matrix bot, scheduler). Pushing untested code there risks breaking a running bot. Instead, use **git worktrees** for feature branches:

```bash
cd ~/Hestia-runtime
git worktree add ../Hestia-feature-mything feature/mything
cd ../Hestia-feature-mything
uv sync
```

Now you have an isolated checkout with its own Python environment, but sharing the same git history.

---

## Isolating state

Each worktree must use **separate** runtime state so branches do not collide:

| Item | Stable runtime | Feature worktree |
|------|---------------|------------------|
| **Database** | `~/Hestia-runtime/hestia.db` | `./runtime-data/hestia.db` |
| **Slots** | `~/Hestia-runtime/slots/` | `./runtime-data/slots/` |
| **Artifacts** | `~/Hestia-runtime/artifacts/` | `./runtime-data/artifacts/` |
| **Config** | `~/Hestia-runtime/config.py` | `./config.py` (copied + edited) |

`runtime-data/` is already gitignored at the repo root (`/runtime-data/` in `.gitignore`).

Example feature config:

```python
from pathlib import Path
from hestia.config import HestiaConfig, InferenceConfig, SlotConfig, StorageConfig

config = HestiaConfig(
    inference=InferenceConfig(base_url="http://localhost:8001", model_name="..."),
    slots=SlotConfig(slot_dir=Path("runtime-data/slots"), pool_size=4),
    storage=StorageConfig(
        database_url="sqlite+aiosqlite:///runtime-data/hestia.db",
        artifacts_dir=Path("runtime-data/artifacts"),
        allowed_roots=["."],
    ),
)
```

Initialize the feature database once:

```bash
hestia --config config.py init
```

---

## Matrix test room

Never point a feature worktree at the **production** Matrix room. Create a dedicated test room:

1. Create a room on your homeserver.
2. Invite the bot account.
3. Put the room ID in the feature config's `MatrixConfig.allowed_rooms` (or `.matrix.secrets.py`).
4. Run `hestia --config config.py matrix` from the worktree.

---

## Merge discipline

1. **Run tests in the worktree** before opening a PR/merge:
   ```bash
   uv run pytest tests/unit/ tests/integration/ -q
   ```
2. **Fast-forward merge to `develop`** (or rebase) — no merge commits for feature branches in this repo.
3. **Pull `develop` into `~/Hestia-runtime`** only after green tests and Cursor review.
4. **Restart systemd services** in the runtime tree after pulling:
   ```bash
   sudo systemctl restart hestia-agent@$USER
   ```

---

## Quick reference

```bash
# Add worktree
git worktree add ../Hestia-feature-X feature/X
cd ../Hestia-feature-X
uv sync

# Remove worktree when done
cd ~/Hestia-runtime
git worktree remove ../Hestia-feature-X
rm -rf ../Hestia-feature-X
```
