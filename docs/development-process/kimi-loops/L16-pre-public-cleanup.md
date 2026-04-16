# Kimi loop L16 — Pre-public cleanup (docs, polish, scaffolding removal)

## Review carry-forward

- **Lazy `import base64` in `artifacts/store.py`:** L15 added `os` and `tempfile` at module level but left `import base64` inside `_save_inline_index()`. Move it to module level in §5.
- **Pre-existing ruff debt:** 165 ruff errors across the codebase (pre-existing, not from L15). Not in scope for this loop.
- **aiosqlite thread warnings:** Pre-existing pytest housekeeping item. Not blocking.
- **L15 changed `_is_url_safe` to skip DNS resolution** — the docstring update is good, no further carry-forward.

**Branch:** `feature/l16-pre-public-cleanup` from **`develop`** (includes **L15**).

---

## Goal

Remove internal scaffolding, fix documentation gaps, and polish code style issues identified in the pre-public code review. After this loop, the repo is ready for public release.

---

## §-1 — Create branch

```bash
git checkout develop
git pull origin develop
git checkout -b feature/l16-pre-public-cleanup
```

---

## §1 — Archive handoff state files to vault

### Problem

`docs/HANDOFF_STATE.md` and the entire `docs/handoffs/` directory are internal AI session handoff notes. They expose the development workflow and will confuse contributors.

### Fix

1. Create `vault/Projects/Hestia-Handoff-Archive/` in Dylan's home vault directory.
2. **Move** (not delete) all files:
   - `docs/handoffs/*.md` → `vault/Projects/Hestia-Handoff-Archive/handoffs/`
   - `docs/HANDOFF_STATE.md` → `vault/Projects/Hestia-Handoff-Archive/HANDOFF_STATE.md`

**IMPORTANT:** Since `vault/` is outside the repo (at `~/vault/`), this is a two-step process:
1. Copy the files to `~/vault/Projects/Hestia-Handoff-Archive/` (preserving directory structure).
2. `git rm` the files from the repo.
3. Also remove any references to `HANDOFF_STATE.md` or `docs/handoffs/` from other docs that are staying in the repo (e.g. the `.cursorrules` or orchestration docs — but those are internal too and may also be cleaned). Leave the `docs/orchestration/` directory as-is (it documents the build process, which is interesting for contributors).

**Also remove:** `docs/orchestration/kimi-loop-log.md` and `docs/orchestration/kimi-phase-queue.md` — these are internal orchestration state. Move them to the vault archive alongside the handoffs. Keep `docs/orchestration/kimi-loops/` directory (the specs themselves document design decisions and are useful history).

**Actually, reconsider:** The entire `docs/orchestration/` tree is internal scaffolding: loop specs, queue files, log files. Move the whole directory to the vault archive. The design documents in `docs/design/` are the useful ones.

Wait — **do NOT move `docs/orchestration/` yet**. It's actively used by the Kimi loop system. Only move `docs/handoffs/` and `docs/HANDOFF_STATE.md` for now. The orchestration cleanup happens after the queue is fully done (post-L16).

### What to move

```
docs/handoffs/*.md         → ~/vault/Projects/Hestia-Handoff-Archive/handoffs/
docs/HANDOFF_STATE.md      → ~/vault/Projects/Hestia-Handoff-Archive/
```

### What to git rm

```
git rm -r docs/handoffs/
git rm docs/HANDOFF_STATE.md
```

### Tests

None needed — this is a docs-only change. Verify `uv run pytest tests/unit/ tests/integration/ -q` still passes (no test references these files).

**Commit:** `docs: archive internal handoff state files (pre-public cleanup)`

---

## §2 — Document skills system as work-in-progress

### Problem

The `@skill` decorator, `SkillStore`, `SkillIndexBuilder`, `SkillState` are all defined and tested, but there's no `run_skill` meta-tool, no built-in skills, and the README doesn't mention the feature. It looks like abandoned scaffolding.

### Fix

1. **Add a Skills section to README.md** (after the "What it can do" section or under a "Roadmap" heading), clearly marked as experimental/WIP:

```markdown
### Skills (experimental)

Hestia includes a skills framework for defining multi-step workflows as decorated Python functions. Skills declare their required tools and capabilities, and can be indexed for inclusion in the system prompt.

```python
from hestia.skills import skill, SkillState

@skill(
    name="daily_briefing",
    description="Summarize today's calendar and weather",
    required_tools=["http_get", "memory_search"],
    state=SkillState.DRAFT,
)
async def daily_briefing(context):
    ...
```

This system is functional but not yet integrated into the orchestrator's tool-calling flow. A `run_skill` meta-tool and built-in skill library are planned for a future release. See [ADR-024](docs/adr/ADR-024-skills-user-defined-python-functions.md) for the design rationale.
```

2. **Add `SkillState.EXPERIMENTAL`** if it doesn't exist, or keep using `DRAFT`. The key point is the README is honest about the state.

**Commit:** `docs: document skills system as experimental/WIP in README`

---

## §3 — Move asyncpg to optional dependency

### Problem

`asyncpg>=0.31.0` is in the main `dependencies` list, but PostgreSQL support is undocumented. Most users will use SQLite. Having it as a hard dependency pulls in unnecessary packages.

### Fix

1. In `pyproject.toml`, move `asyncpg` from `dependencies` to an optional extras group:

```toml
[project.optional-dependencies]
postgres = ["asyncpg>=0.31.0"]
```

2. In `src/hestia/persistence/db.py`, add a helpful error message if someone uses a `postgresql+asyncpg://` connection string without having asyncpg installed:

```python
if url.startswith("postgresql") and not _asyncpg_available():
    raise ImportError(
        "PostgreSQL support requires the 'postgres' extra: "
        "pip install hestia[postgres]"
    )
```

Where `_asyncpg_available()` does a try/except ImportError on asyncpg.

3. Update the README **Security** or **Configuration** section to mention PostgreSQL is available via `pip install hestia[postgres]` or `uv sync --extra postgres`.

**Commit:** `refactor: move asyncpg to optional postgres extra`

---

## §4 — Update README security section

### Problem

The security section doesn't mention that Python-based config files execute arbitrary code (full RCE via `exec_module()`). For personal use this is intentional, but it should be called out.

### Fix

Add to the Security section in `README.md`:

```markdown
**Config file execution.** Hestia config files are Python modules loaded via `importlib`. This means a config file can execute arbitrary code — this is intentional (it lets you compute config values, import secrets from environment variables, etc.), but you should treat config files with the same caution as any executable script. Never load a config file from an untrusted source.
```

**Commit:** `docs: add config file execution security note to README`

---

## §5 — Move lazy imports to module level

### Problem

Several files use lazy imports inside function bodies (`import re`, `import base64`, `import httpx`). Python caches imports so there's no performance cost, but it's inconsistent with the rest of the codebase.

### Files to fix

1. **`src/hestia/tools/builtin/http_get.py`** — `import httpx` inside the function body. Move to top of file.
2. **`src/hestia/artifacts/store.py`** — `import base64` inside two methods. Move to top of file.
3. **`src/hestia/orchestrator/engine.py`** — `import re` inside a function. Move to top of file.
4. **`src/hestia/persistence/trace_store.py`** — `import json` inside three methods. Move to top of file.

For each file: add the import to the top-level imports and remove the inline `import` statement.

### Tests

Run full test suite — no behavior change expected.

**Commit:** `refactor: move lazy imports to module level`

---

## §6 — Default model_name validation

### Problem

`InferenceConfig` has `model_name: str = "Qwen3.5-9B-UD-Q4_K_XL.gguf"`. Most users won't have this exact file. An empty default with a validation error would be clearer.

### Fix

In `src/hestia/config.py`, change:

```python
model_name: str = "Qwen3.5-9B-UD-Q4_K_XL.gguf"
```

to:

```python
model_name: str = ""
```

Then in the inference client or CLI startup path, add validation:

```python
if not config.inference.model_name:
    raise ValueError(
        "inference.model_name is required — set it to your llama.cpp model filename "
        "(e.g. 'my-model-Q4_K_M.gguf')"
    )
```

The best place for this check is in `InferenceClient.__init__()` or in the CLI's `chat` / `telegram` / `matrix` commands before creating the client.

**Also update `deploy/example_config.py`** (or any example configs) to show a realistic model_name value with a comment explaining it must match their model file.

### Tests

1. `test_empty_model_name_raises` — verify that creating an InferenceClient with empty model_name raises ValueError.
2. Update any tests that rely on the default model_name to set it explicitly.

**Commit:** `fix: require explicit model_name instead of hardcoded default`

---

## §7 — Reorder README quickstart

### Problem

The Quickstart jumps to `hestia init` and `hestia chat`, but llama.cpp must already be running or the tool immediately fails with a connection error. The hardware setup section comes after the quickstart.

### Fix

Add a **Prerequisites** block before the quickstart commands:

```markdown
## Quickstart

### Prerequisites

Hestia connects to a [llama.cpp](https://github.com/ggerganov/llama.cpp) server for inference. Start it before running Hestia:

```bash
# Download and build llama.cpp (see their README for details)
# Then start the server with your model:
llama-server -m your-model.gguf -c 8192 --port 8001
```

Hestia connects to `http://localhost:8001` by default. See [Running on your hardware](#running-on-your-hardware) for GPU-specific options.

### Install and run

```bash
git clone ...
```
```

The existing "Running on your hardware" section stays where it is but now the quickstart doesn't leave users stranded.

**Commit:** `docs: add llama.cpp prerequisite to quickstart`

---

## Handoff

`docs/handoffs/HESTIA_L16_REPORT_<YYYYMMDD>.md` + `.kimi-done` with:

```
HESTIA_KIMI_DONE=1
LOOP=L16
BRANCH=feature/l16-pre-public-cleanup
COMMIT=<sha>
TESTS=<pass count>
```

**NOTE:** The handoff report for L16 goes in `docs/handoffs/` (since it's the last loop — §1 removes the old ones, this new one documents the final state). Actually — the handoff report should go to the vault archive path instead, since §1 removes `docs/handoffs/` from the repo. Write it to `~/vault/Projects/Hestia-Handoff-Archive/handoffs/HESTIA_L16_REPORT_<YYYYMMDD>.md` and also put a brief summary in `.kimi-done`.

---

## Critical rules recap

1. **No secrets in code.** Never hardcode tokens, passwords, or API keys.
2. **Every section gets its own commit** with the message shown above.
3. **Run `uv run pytest tests/unit/ tests/integration/ -q`** after each commit. All must pass.
4. **Run `uv run ruff check src/ tests/`** — fix any new violations.
5. Write the `.kimi-done` file and handoff report **last**.
6. Do NOT modify files outside the scope of this spec.
7. Do NOT skip carry-forward items.
8. The `~/vault/` directory is outside the git repo — use absolute paths.
