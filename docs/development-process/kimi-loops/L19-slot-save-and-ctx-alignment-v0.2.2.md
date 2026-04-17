# Kimi loop L19 — slot-save basename fix + ctx-window alignment + KV-cache docs → v0.2.2

## Review carry-forward

Issues surfaced while exposing Hestia to a real llama-server (Hermes-shared) on a 3060 12GB during L18 post-release runtime setup:

- Tool-call traces don't yet seem to pick up `save_memory` after http_get in the runtime — probably because no memory saves have happened yet. Monitor; not a code issue.
- `config.runtime.py` had to be extended by hand to wire MatrixConfig from `.matrix.secrets.py`. Not necessarily a bug — that file is user-owned — but the example config in `deploy/` should make the full pattern obvious. Consider adding a deploy-level example that reads all platform secrets from files or env vars. **Not in scope for L19.**
- Per-artifact metadata file is atomic (L18 §2) but there is still no index/CRC for on-disk `{handle}.json` files — a manual file edit that writes invalid JSON still surfaces as `JSONDecodeError` at read time, not `ArtifactNotFoundError`. **Not in scope for L19.** Track in a future loop if it keeps biting.

**Branch:** `feature/l19-slot-save-and-ctx-alignment` from **`develop`**.

---

## Goal

Three real bugs exposed by running v0.2.1 against a live llama-server:

1. **Slot-save/restore sends absolute paths to llama.cpp, which rejects them with 400 "Invalid filename"** — every turn ends in an error log, no session state is persisted to disk, `evict()` can never save. Real runtime-breaking bug.
2. **`DefaultPolicy.ctx_window` default is 32768 but is never wired from `HestiaConfig`**, so regardless of the user's actual llama-server `--ctx-size / --parallel` settings, the policy thinks it has 32K per slot. On a typical 12GB 3060 setup (`-c 49152 -np 3`), real per-slot budget is 16K — the policy over-commits by 2×.
3. **README quickstart shows `--cache-type-k q4_0 --cache-type-v q4_0`**, but `deploy/hestia-llama.service` and `deploy/README.md` use `turbo3` as the default for 12GB. Public docs contradict the canonical deploy.

Plus version bump and v0.2.2 patch release.

---

## §-1 — Create branch and capture baseline

```bash
git checkout develop
git pull origin develop
git checkout -b feature/l19-slot-save-and-ctx-alignment
uv run pytest tests/unit/ tests/integration/ -q
```

Record the baseline ("478 passed, 6 skipped" expected — matches v0.2.1).

---

## §1 — Fix slot-save / slot-restore to pass basename only

### Problem

`src/hestia/inference/slot_manager.py` calls `self._inference.slot_save(slot_id, str(saved_path))` where `saved_path = self._slot_path_for(session.id)` returns a full absolute `Path` under `cfg.slots.slot_dir`. That full path is then POSTed to llama.cpp as:

```json
POST /slots/{id}?action=save
{"filename": "/home/dylan/.../runtime-data/slots/telegram_xxx.bin"}
```

llama.cpp rejects any `filename` containing a path separator (path-traversal guard) and returns:

```
400 {"error":{"code":400,"message":"Invalid filename","type":"invalid_request_error"}}
```

Confirmed with a live llama-server curl:

```bash
# Absolute path → 400
curl -X POST 'http://.../slots/0?action=save' -d '{"filename": "/abs/path.bin"}'
# Basename → 200
curl -X POST 'http://.../slots/0?action=save' -d '{"filename": "session.bin"}'
```

The file is written to wherever `llama-server --slot-save-path` points. Hestia must pass only the **basename**; the directory part is the server's responsibility.

This affects:

- `SlotManager.save()` (periodic checkpoint)
- `SlotManager._evict_session_locked()` (eviction save)
- `SlotManager._restore_into_slot()` / any call site of `slot_restore` that uses `session.slot_saved_path` — same basename rule applies on restore.

### Fix

**File:** `src/hestia/inference/slot_manager.py`

In `save()` (~line 142):

```python
saved_path = self._slot_path_for(session.id)
async with self._lock:
    # llama.cpp rejects path separators in `filename`; pass basename only.
    # Actual on-disk location is controlled by llama-server's --slot-save-path.
    await self._inference.slot_save(session.slot_id, saved_path.name)
await self._store.update_saved_path(session.id, saved_path.name)
```

In `_evict_session_locked()` (~line 183):

```python
saved_path = self._slot_path_for(session_id)
await self._inference.slot_save(slot_id, saved_path.name)
await self._inference.slot_erase(slot_id)
await self._store.release_slot(
    session_id,
    demote_to=SessionTemperature.WARM,
    saved_path=saved_path.name,
)
```

Restore sites (`acquire()` around lines 94 and 119) currently pass `session.slot_saved_path` directly. If L15+ and earlier commits wrote absolute paths into the DB column, those are now poisoned. Two defensive steps:

1. In the restore call, extract the basename defensively even if `slot_saved_path` is a full path:

   ```python
   filename = Path(session.slot_saved_path).name
   await self._inference.slot_restore(slot_id, filename)
   ```

2. Add a **one-time migration** that rewrites any existing `sessions.slot_saved_path` values containing path separators down to their basename. Place the migration under `src/hestia/persistence/migrations/` following the existing pattern. If that directory is Alembic-driven, generate a revision with `uv run alembic revision -m "normalize_slot_saved_path_to_basename"` and write the upgrade as:

   ```python
   op.execute("""
       UPDATE sessions
       SET slot_saved_path = substr(slot_saved_path, length(rtrim(slot_saved_path, replace(slot_saved_path, '/', ''))) + 1)
       WHERE slot_saved_path IS NOT NULL AND slot_saved_path LIKE '%/%'
   """)
   ```

   If not Alembic-driven, add the normalization to whatever the existing migration mechanism is. **Check `src/hestia/persistence/` for the current pattern before writing this.**

### Also clarify `SlotConfig.slot_dir` semantics

**File:** `src/hestia/config.py`

Amend the `SlotConfig.slot_dir` docstring to say:

> Directory where llama-server persists slot snapshots. **Must match
> `llama-server --slot-save-path`.** Hestia sends only the basename to
> llama.cpp; llama-server writes the file here. Hestia itself does not
> write to this directory — it is purely a declaration of where slot
> files will land so that out-of-band cleanup (gc, TTL, etc.) knows
> where to look.

This is a user-facing semantic change — the directory was previously implied to be "Hestia-owned". Make it explicit.

### Tests

**File:** `tests/unit/test_slot_manager.py` (or create if not already present).

Add these tests, mocking `InferenceClient`:

1. `test_slot_save_sends_basename_only` — assert `InferenceClient.slot_save` is called with the basename (no `/` in the argument), regardless of `slot_dir`.
2. `test_slot_restore_normalizes_legacy_absolute_paths` — seed a `Session` with `slot_saved_path = "/old/abs/path/session_x.bin"`; assert restore is called with `"session_x.bin"`.
3. `test_evict_stores_basename_in_db` — after eviction, assert `SessionStore.release_slot` is called with `saved_path` being a basename.
4. `test_update_saved_path_stores_basename` — after `save()`, assert `update_saved_path` got the basename.

Also add a **live integration test** guarded behind `@pytest.mark.skipif(no_llama_server, ...)` that POSTs to an actual slot endpoint — but this is optional for this loop; don't block on it.

**Commit:** `fix(slot-manager): pass basename to llama.cpp; normalize legacy absolute paths`

---

## §2 — Wire `ctx_window` from config into the policy engine

### Problem

`src/hestia/policy/default.py:25` — `DefaultPolicyEngine.__init__` takes `ctx_window: int = 32768`.

`src/hestia/cli.py:301` currently constructs the engine without passing `ctx_window`:

```python
policy = DefaultPolicyEngine(
    default_reasoning_budget=cfg.inference.default_reasoning_budget
)
```

So the policy *always* uses 32768, regardless of the real per-slot ctx. On a 3060 12GB running `-c 49152 -np 3` (shared with Hermes), real per-slot budget is **16384** — Hestia over-commits by 2×. On deploy's own `deploy/hestia-llama.service` (`--ctx-size 16384 -np 4`), it is 4× over.

`src/hestia/audit/checks.py:231` also instantiates a bare `DefaultPolicyEngine()` for audit purposes — same 32768 fallback. Lower priority but worth the consistency pass.

### Fix

**File:** `src/hestia/config.py`

Add a field to `InferenceConfig`:

```python
@dataclass
class InferenceConfig:
    ...
    context_length: int = 16384  # Per-slot context budget; should equal llama-server's `--ctx-size` / `--parallel`
    default_reasoning_budget: int = 2048
    ...
```

Document this clearly in the docstring — **per-slot**, not total. Most users will see this default and bump it if they know their llama-server is configured for more.

**File:** `src/hestia/cli.py`

Update the `DefaultPolicyEngine` construction at ~line 301:

```python
policy = DefaultPolicyEngine(
    ctx_window=cfg.inference.context_length,
    default_reasoning_budget=cfg.inference.default_reasoning_budget,
)
```

Also update `src/hestia/audit/checks.py:231` to accept a config-aware engine if one is available; if the audit path does not yet have a `HestiaConfig` handle, leave a TODO and stick with the default for this loop.

**File:** `src/hestia/policy/default.py`

Change the default of `ctx_window` to `16384` (matches `InferenceConfig.context_length`'s new default) and update the docstring:

```python
def __init__(
    self, ctx_window: int = 16384, default_reasoning_budget: int = 2048
) -> None:
    """Initialize with context window size.

    Args:
        ctx_window: **Per-slot** context window in tokens. Must match
            your llama-server's `--ctx-size / --parallel`. Default
            (16K) matches `deploy/hestia-llama.service` out of the box.
        ...
    """
```

### Tests

**File:** `tests/unit/test_policy_default.py` (or wherever the existing policy tests live).

1. `test_ctx_window_default_is_16k` — assert `DefaultPolicyEngine().ctx_window == 16384`.
2. `test_turn_token_budget_uses_ctx_window` — construct with `ctx_window=8192`, assert `turn_token_budget(None)` reflects the smaller ceiling.
3. `test_cli_passes_ctx_window_from_config` — build a fake `HestiaConfig` with `inference.context_length=32768`, wire through the CLI's policy-construction helper (refactor if needed so this is testable without running the whole CLI), assert the resulting engine has `ctx_window == 32768`.

### Runtime settings worth updating too (non-code)

Worth mentioning in the CHANGELOG as a note to operators:

- `deploy/hestia-llama.service` currently has `--ctx-size 16384 --slots 4` → 4 slots × 4096 = too small. Suggest bumping to `--ctx-size 16384 --slots 2` (two slots of 8K) OR `--ctx-size 32768 --slots 4` (four slots of 8K). **Match the default with the deploy.** Kimi may pick either; update **both** the policy default and the deploy ExecStart so they agree.

  Recommended (matches what 12GB/turbo3 can actually sustain):

  ```
  --ctx-size 32768 --parallel 4 --cache-type-k turbo3 --cache-type-v turbo3
  ```

  Per-slot = 8192. Set `InferenceConfig.context_length = 8192` and `DefaultPolicyEngine(ctx_window=8192)` as defaults.

  If Kimi picks different numbers that's fine — just ensure deploy, config default, and policy default all agree.

**Commit:** `fix(policy): wire ctx_window from HestiaConfig; correct per-slot default`

---

## §3 — Fix README / deploy KV-cache quant inconsistency

### Problem

`README.md` quickstart shows:

```
--cache-type-k q4_0 \
--cache-type-v q4_0 \
```

`deploy/hestia-llama.service` uses `turbo3` (shipped in mainline llama.cpp, more VRAM-efficient than q4_0 on RTX 30/40 series). `deploy/README.md` documents `turbo3` as the 12GB default.

The public README contradicts the canonical deploy. A user following README gets sub-optimal VRAM usage and may conclude Hestia needs more VRAM than it does.

### Fix

**File:** `README.md`

In the llama-server example flags section (around lines 306–313), change to:

```bash
--cache-type-k turbo3 \
--cache-type-v turbo3 \
```

Update the explanatory sentence:

> The flags that matter: `-np 4` sets 4 KV-cache slots (match `SlotConfig.pool_size`). `--cache-type-k turbo3` and `--cache-type-v turbo3` quantize the KV-cache to ~3 bits per value (more compact than the older `q4_0`), which roughly doubles the context you can fit in the same VRAM on RTX 30/40-series GPUs. `--slot-save-path` enables save/restore so Hestia can checkpoint and resume sessions from disk.

If turbo3 is mentioned elsewhere in README.md or in docs, scan once with `rg -n 'q4_0' docs/ README.md` and pick each mention to either update or annotate (e.g. "older llama.cpp releases used q4_0 as the default; turbo3 is preferred on supported cards").

**File:** `deploy/README.md`

Line 181 example suggests q4_0 for very low VRAM — leave as-is (q4_0 is still correct for <8GB cards where turbo3 may not give benefits and older hardware support is iffy). Just add a sentence after the table saying turbo3 requires CUDA compute 7.5+ / RDNA 2+ if that's accurate, otherwise leave it alone. **Do not change the deploy/README.md table.**

**Commit:** `docs(readme): align quickstart KV-cache quant with deploy (turbo3)`

---

## §4 — Optional: align deploy `hestia-llama.service` with the new defaults

If you change `InferenceConfig.context_length` and `DefaultPolicyEngine(ctx_window=...)` defaults, update `deploy/hestia-llama.service` `ExecStart` to match. Whatever pairing Kimi picks in §2, make them agree here too.

No test changes for this section.

**Commit:** `deploy: align llama.service ctx-size and parallel with new policy default`

---

## §5 — CHANGELOG + version bump to v0.2.2

**File:** `CHANGELOG.md`

Add at the top (above `[0.2.1]`):

```markdown
## [0.2.2] — 2026-04-17

### Fixed
- `SlotManager` now passes only the basename of a slot file to llama.cpp's
  `/slots?action=save|restore` endpoint. Previously Hestia sent absolute
  paths, which llama.cpp rejects (HTTP 400 "Invalid filename"), causing
  every turn to log an error and no session state ever reached disk. A
  one-time migration normalizes any existing `sessions.slot_saved_path`
  values to basenames.
- `DefaultPolicyEngine.ctx_window` is now wired through `HestiaConfig.inference.context_length`
  (new field). Previously the policy always used the 32768 default
  regardless of the user's actual llama-server `--ctx-size / --parallel`
  settings, silently over-committing the turn token budget on typical
  12GB deployments.

### Changed
- `SlotConfig.slot_dir` docstring clarified: this must match llama-server's
  `--slot-save-path`. Hestia does **not** write to this directory; it is
  a declaration so out-of-band cleanup knows where to look.
- README quickstart now shows `turbo3` KV-cache quantization (matching
  `deploy/hestia-llama.service`), not `q4_0`.
- `DefaultPolicyEngine.ctx_window` default changed from 32768 to 16384 to
  match `deploy/hestia-llama.service` out of the box. Users on larger
  servers should set `InferenceConfig.context_length` explicitly.
```

**File:** `pyproject.toml`

Bump version `"0.2.1"` → `"0.2.2"`.

**File:** `uv.lock`

Run `uv sync`.

**Commit:** `chore: prep v0.2.2 release`

---

## §6 — Promote develop → main, tag v0.2.2, push

Same pattern as L17 and L18.

```bash
# 6a Final test pass on feature branch
git checkout feature/l19-slot-save-and-ctx-alignment
uv run pytest tests/unit/ tests/integration/ -q
uv run ruff check src/ tests/   # no new violations

# 6b Merge feature → develop
git checkout develop
git merge --no-ff feature/l19-slot-save-and-ctx-alignment \
    -m "Merge L19 — slot-save fix + ctx-window alignment + v0.2.2 prep"
git push origin develop

# 6c Promote develop → main
git checkout main
git pull origin main
git merge --no-ff develop -m "Release v0.2.2

Patch release.

- Fix slot-save/restore to pass basename (fixes HTTP 400 on every turn)
- Wire ctx_window from InferenceConfig.context_length into DefaultPolicy
- Correct README KV-cache quant example (turbo3) to match deploy

See CHANGELOG.md for full detail."

# 6d Tag
git tag -a v0.2.2 -m "Hestia v0.2.2 — patch release: slot-save fix, ctx-window wiring, docs."

# 6e Push
git push origin main
git push origin v0.2.2

# 6f Confirm
git log -1 --oneline main
git log -1 --oneline develop
git tag -l | sort
```

Expected tags: `development-history-snapshot`, `v0.0.0`, `v0.1.0`, `v0.2.0`, `v0.2.1`, `v0.2.2`.

---

## §7 — Branch cleanup + final verification

```bash
git branch -d feature/l19-slot-save-and-ctx-alignment
git push origin --delete feature/l19-slot-save-and-ctx-alignment 2>/dev/null || true
git remote prune origin

git checkout main
uv run pytest tests/unit/ tests/integration/ -q    # must pass baseline + new tests
git checkout develop
uv run pytest tests/unit/ tests/integration/ -q    # must pass identically
```

---

## Handoff

Write `.kimi-done` (do **not** commit):

```
HESTIA_KIMI_DONE=1
SPEC=docs/development-process/kimi-loops/L19-slot-save-and-ctx-alignment-v0.2.2.md
LOOP=L19
BRANCH=develop
PYTEST_BASELINE=<from §-1>
PYTEST_FINAL_DEVELOP=<from §7>
PYTEST_FINAL_MAIN=<from §7>
GIT_HEAD_DEVELOP=<rev-parse develop>
GIT_HEAD_MAIN=<rev-parse main>
TAG_V022=<rev-parse v0.2.2>
SLOT_SAVE_FIX=done
CTX_WINDOW_WIRED=done
README_CACHE_QUANT=done
MIGRATION_REVISION=<alembic rev or "inline" or "none">
```

---

## Critical rules recap

1. **No secrets.** `.matrix.secrets.py`, `.env`, and any `HESTIA_TELEGRAM_BOT_TOKEN` value must NEVER enter a commit. `.gitignore` already covers them — just be careful with pytest fixture generation.
2. **One commit per section** with the messages above.
3. **`uv run pytest tests/unit/ tests/integration/ -q`** green after every commit.
4. **`uv run ruff check src/ tests/`** — no new violations.
5. **§1 is the real fix.** Don't be tempted to "fix it in config" by changing `_slot_path_for` to return a bare string — `slot_dir` is still useful for local bookkeeping and tooling. The fix is to send the basename to llama.cpp explicitly.
6. **Per-slot vs. total context is the critical semantic** for §2. The field on `InferenceConfig` represents the **per-slot** budget, not total `--ctx-size`. Name and document accordingly.
7. **Numbers in policy default, deploy service file, and README must agree.** If §2 picks 8K per slot, §4 must use it too, and README examples must not contradict.
8. **`.kimi-done` last.** Only after §6 push succeeds and §7 verification is clean.
9. **Stop and report immediately on any phase failure.** §6 (release) is only attempted after §1–§5 are all green.
