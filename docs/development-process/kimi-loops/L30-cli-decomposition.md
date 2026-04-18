# Kimi loop L30 — cli.py decomposition + bootstrap module

## Review carry-forward

(Cursor populates after L29 review.)

From **external code-quality review (2026-04-18)**, verified against `develop`:

- `src/hestia/cli.py` is **2,569 lines** and conflates three concerns: (a) subsystem bootstrapping (the `cli()` group function is ~200+ lines of constructor wiring), (b) platform-specific runtime (`run_telegram` and `run_matrix` are ~120 lines each, ~85% identical), (c) actual `@click.command` definitions.
- The `cli()` group instantiates an `InferenceClient` (which spins up an `httpx.AsyncClient`) **on every invocation**, including `hestia version` and `hestia health`. Lazy.
- `Orchestrator(...)` is constructed in **4 places** with **inconsistent** arg sets (Cursor verified that `style_store`/`style_config` were missing from at least one call site historically). Adding a 13th dependency means hand-editing 4 files.
- `ctx.obj` carries a typed `CliAppContext` **and** all the same fields as raw dict entries (`ctx.obj["config"]`, `ctx.obj["inference"]`, …). The dict path is already stale (`ctx.obj["style_builder"]` exists; `ctx.obj["handoff_summarizer"]` does not). `schedule_daemon`, `run_telegram`, `run_matrix` use the dict path and bypass the typed object.
- Every CLI command begins with `await app.bootstrap_db()` and an `asyncio.run` shim. Boilerplate × ~30 commands.

**Branch:** `feature/l30-cli-decomposition` from **`develop`** (post-L29 merge).

**Target version:** **0.7.4** (patch — no public API change; CLI surface preserved).

---

## Goal

Split `cli.py` into:

- `src/hestia/app.py` — `make_app(config) -> CliAppContext`; sole owner of subsystem wiring; lazy/optional inference instantiation; idempotent `bootstrap_db()`.
- `src/hestia/platforms/runners.py` — `run_telegram(app, config)` and `run_matrix(app, config)`; share confirmation-callback construction and the polling-loop scaffold.
- `src/hestia/cli.py` — **only** Click definitions and command bodies. **Target ≤ 600 lines.**

`CliAppContext.make_orchestrator()` becomes the **single** Orchestrator constructor; eliminate every direct `Orchestrator(...)` call elsewhere. Drop the raw `ctx.obj["..."]` dict layer entirely.

This is a **pure refactor**. No behavior changes. No new commands. Test suite must remain identical (no test edits except to import paths and possibly a few `monkeypatch` targets).

---

## Scope

### §-1 — Merge prep

Branch from `develop` (post-L29 merge). `git status` clean. **Run the full test suite first** and record the baseline number — every following step must preserve it.

### §0 — Cleanup carry-forward

(Cursor populates from L29 review.)

### §1 — Extract `src/hestia/app.py`

New file `src/hestia/app.py` with:

- `@dataclass class CliAppContext` — moved from `cli.py` verbatim. **Add** any fields that `cli.py` currently writes only to `ctx.obj` raw (artifact_store, style_store, scheduler_store, handoff_summarizer, etc.). Cursor confirms these are scattered; one canonical home.
- `def make_app(config: HestiaConfig) -> CliAppContext` — moved from the body of the `cli()` group. **Lazy `inference_client`**: store as `Optional[InferenceClient]`, instantiate on first access via a property.
- `async def bootstrap_db(self) -> None` — idempotent (track `self._bootstrapped: bool`).
- `def make_orchestrator(self) -> Orchestrator` — single constructor. Pull every dependency from `self`.

`cli.py` then imports and uses `make_app`. No Click code moves.

### §2 — Extract `src/hestia/platforms/runners.py`

New file `src/hestia/platforms/runners.py`:

```python
async def run_platform(
    app: CliAppContext,
    config: HestiaConfig,
    *,
    adapter: PlatformAdapter,
    confirm_callback: ConfirmationCallback,
) -> None:
    """Shared platform polling loop. Used by run_telegram and run_matrix."""
    ...

async def run_telegram(app: CliAppContext, config: HestiaConfig) -> None:
    adapter = TelegramAdapter(...)
    confirm_callback = make_telegram_confirm_callback(...)
    await run_platform(app, config, adapter=adapter, confirm_callback=confirm_callback)

async def run_matrix(app: CliAppContext, config: HestiaConfig) -> None:
    adapter = MatrixAdapter(...)
    confirm_callback = make_matrix_confirm_callback(...)
    await run_platform(app, config, adapter=adapter, confirm_callback=confirm_callback)
```

`cli.py` `run_telegram`/`run_matrix` Click commands become 3-line shims that call into `runners.py`.

### §3 — Drop raw `ctx.obj` dict layer

In every command (Cursor: `git grep -n "ctx.obj\[" -- src/hestia/cli.py` to enumerate), replace `ctx.obj["x"]` with `app.x`. Confirm by grep that no raw `ctx.obj["..."]` access remains in `src/hestia/cli.py` after the refactor.

`cli()` group writes only `ctx.obj = app` (the typed object). No parallel dict writes.

### §4 — Single Orchestrator constructor + `make_orchestrator` callers

- Replace every `Orchestrator(...)` call in `cli.py`/`runners.py`/`app.py` with `app.make_orchestrator()`.
- `git grep -n "Orchestrator(" -- src/hestia` should show only the definition (`orchestrator/engine.py`) and `make_orchestrator()`.

### §5 — `run_async` helper + idempotent bootstrap

In `src/hestia/app.py` (or `cli.py` if cleaner):

```python
def run_async(coro_factory):
    """Decorator: wrap a Click command body so the inner async function
    receives `app` and is run inside asyncio.run. Calls bootstrap_db once."""
    @functools.wraps(coro_factory)
    def wrapper(*args, **kwargs):
        ctx = click.get_current_context()
        app = ctx.obj
        async def _runner():
            await app.bootstrap_db()
            return await coro_factory(app, *args, **kwargs)
        return asyncio.run(_runner())
    return wrapper
```

Use it on every command body that currently does the `async def _xxx(): await app.bootstrap_db(); ...; asyncio.run(_xxx())` pattern. Should reduce many command bodies by 3–4 lines each.

### §6 — Sanity: `cli.py` ≤ 600 lines

After all moves, `wc -l src/hestia/cli.py` should be ≤ 600. If above, the split was insufficient (likely some helpers should follow `make_app` into `app.py`).

### §7 — Tests

- `tests/unit/test_app_make_orchestrator.py` — assert `make_app(config).make_orchestrator()` returns an `Orchestrator` whose dependencies match `app.*`.
- `tests/unit/test_app_lazy_inference.py` — assert `app.inference_client` is not constructed on `make_app()`; only on first access.
- `tests/unit/test_bootstrap_db_idempotent.py` — call `bootstrap_db()` twice; assert no duplicate side effects (e.g., re-creating tables).
- `tests/integration/test_runners_smoke.py` — instantiate `run_telegram`/`run_matrix` with mock adapters that exit after one tick; assert no exception.
- **Existing tests must pass unchanged** apart from import path updates if any test imports `CliAppContext` from `hestia.cli` (point to `hestia.app`).

### §8 — Version bump + handoff

- `pyproject.toml` → `0.7.4`.
- `uv lock`.
- `CHANGELOG.md` `## [0.7.4]` — describe the refactor; emphasize no behavior change.
- `docs/adr/ADR-0020-cli-app-runners-split.md` — short ADR documenting why bootstrap moved out of `cli.py`.
- `docs/handoffs/L30-cli-decomposition-handoff.md`.

**Commits:**

- `refactor(app): extract CliAppContext + make_app into hestia/app.py`
- `refactor(platforms): extract platform runners into platforms/runners.py`
- `refactor(cli): drop raw ctx.obj dict layer; use typed app`
- `refactor(orchestrator): consolidate construction in app.make_orchestrator`
- `refactor(cli): add run_async decorator and idempotent bootstrap_db`
- `test(app): cover make_app, lazy inference, bootstrap idempotency, runners smoke`
- `chore(release): bump to 0.7.4`
- `docs(adr): ADR-0020 cli/app/runners split`
- `docs(handoff): L30 cli decomposition report`

---

## Required commands

```bash
uv lock
uv run pytest tests/unit/ tests/integration/ -q     # must match L29 baseline exactly
uv run mypy src/hestia                              # must be 0
uv run ruff check src/hestia tests
wc -l src/hestia/cli.py                             # ≤ 600
git grep -n "Orchestrator(" -- src/hestia | grep -v "^src/hestia/orchestrator/" | grep -v "make_orchestrator"
# ↑ must return no matches
git grep -n 'ctx.obj\[' -- src/hestia/cli.py
# ↑ must return no matches
```

---

## `.kimi-done` contract

```
HESTIA_KIMI_DONE=1
LOOP=L30
BRANCH=feature/l30-cli-decomposition
COMMIT=<sha>
TESTS=passed=N failed=0 skipped=M
MYPY_FINAL_ERRORS=0
```

---

## Critical Rules Recap

- **Pure refactor.** No new behavior. No new commands. No new config fields.
- Test count must equal the L29 baseline. Adding new tests is fine; **regressions are not**.
- One commit per logical step.
- Push and stop. Cursor merges.
