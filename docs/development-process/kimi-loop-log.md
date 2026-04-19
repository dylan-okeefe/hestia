# Kimi ↔ Cursor loop log

**Purpose:** Append a **full** record after each loop instance: Kimi run finished → Cursor review → follow-up prompt or merge / next task.

**Chat:** In the Cursor thread, give only a **short** bullet summary; put the detailed narrative, commands, file paths, and verdict notes **here**.

**How to append:** Add a new `## YYYY-MM-DD — …` section at the **top** (below this preamble), so the newest loop is always first.

---

## 2026-04-19 — Loop: L37 — code cleanup sweep + ruff baseline 43 → 23 (clean Kimi run; one theme per commit) → merged to develop

**Kimi:** Clean run, 4 commits exactly to budget, ~17 minutes wall time (`exit_code: 0`, `elapsed_ms: 1017597`). Valid `.kimi-done` with `LOOP=L37`, `COMMIT=976441a`, `TESTS=778 passed, 6 skipped`, `MYPY_FINAL_ERRORS=0`. **Second overnight loop landed cleanly.**

**What shipped (one theme per commit):**

- `d0f69bb refactor(engine+platforms+commands)`: removed dead `hasattr()` probes on typed dataclasses inside `_build_failure_bundle` (engine.py); same pattern in `slot_snapshot`; deleted the no-op `app = app if isinstance(app, CliAppContext) else app` in `run_platform` (mypy is satisfied without it); fixed the `_cmd_schedule_add` over-indent in `commands.py`. (Copilot #5/7/10)
- `60898e4 refactor(cli)`: hoisted `schedule_disable`, `schedule_remove`, and `init` from `cli.py` inline bodies into `_cmd_schedule_disable`, `_cmd_schedule_remove`, `_cmd_init` in `commands.py`. `cli.py`'s wrappers are now thin `@run_async` delegations matching every other command. (Copilot #8)
- `04453b1 style(ruff)`: 20 fixes across `audit/checks.py`, `memory/epochs.py`, `platforms/base.py`, `policy/default.py`, etc. **No `# noqa` introduced** — every fix is a real code improvement or mechanical line break.
- `976441a chore(release)`: pyproject `0.8.1.dev0` → `0.8.1.dev1`; uv.lock synced; 40-line handoff with the per-file ruff before/after table.

**Review (Cursor):**

- Diff is 12 files, +187 / -116. All in scope. No new test files.
- Re-ran full gate: **778 passed, 6 skipped** (unchanged). `mypy src/hestia` → **0 errors in 91 source files**. `ruff check src/` → **23** (down 20 — exactly hit spec's "fix at least 20" target). Spot-checked the handoff's ruff before/after table — accurate.
- The audit/checks.py note in the handoff is interesting: Kimi removed an unused `suspicious_writes` variable AND touched the `check_path_allowed` import to silence F401 — this is the right move (the import has a side effect).

**Merge:** `feature/l37-code-cleanup-sweep` → `develop` via `--no-ff` merge commit `c44544f`.

**Queue advance:** `KIMI_CURRENT.md` → **L38** (delegation keyword consolidation + `*_disable` persistence audit — final overnight loop).

---

## 2026-04-19 — Loop: L36 — `app.py` decomposition: extract `commands.py` (clean Kimi run; behavior-preserving refactor) → merged to develop

**Kimi:** Clean run, 3 commits, ~14 minutes wall time (`exit_code: 0`, `elapsed_ms: 858221`). Valid `.kimi-done` with `LOOP=L36`, `COMMIT=0c98048`, `TESTS=778 passed, 6 skipped`, `MYPY_FINAL_ERRORS=0`. **First overnight loop landed cleanly.**

**What shipped:**

- `src/hestia/commands.py` (new, 1,060 lines) — every `_cmd_*` async/sync function moved verbatim from `app.py`. Imports updated to absolute (no `.app` self-references).
- `src/hestia/app.py` — collapsed from **1,533 → 517 lines** (-1,016, -66%). Now hosts only infrastructure: `CliAppContext`, `make_app`, `run_async`, `CliResponseHandler`, `_compile_and_set_memory_epoch`, `_handle_meta_command`, `_require_scheduler_store`. The self-referential `from hestia.app import CliResponseHandler` inside `_cmd_chat`/`_cmd_ask` is gone (commands.py imports it once at module scope).
- `src/hestia/cli.py` — the `from hestia.app import (_cmd_*…)` block is now `from hestia.commands import (_cmd_*…)`.
- `pyproject.toml`: `0.8.0` → `0.8.1.dev0` (signals post-release dev work; not a release tag). `uv.lock` synced in the same commit chain.
- `docs/handoffs/L36-app-commands-split-handoff.md` (new, 34 lines).

**Review (Cursor):**

- Diff is mechanical. Net add of just 56 lines (mostly module docstring + import lines in commands.py). No new tests because the refactor is import-path-only.
- No test files needed import-path updates — none of the unit/integration tests import `_cmd_*` from `hestia.app` directly (they all go through CliRunner against `cli.py`).
- Re-ran full gate: **778 passed, 6 skipped** (unchanged from L35d). `mypy src/hestia` → **0 errors in 91 source files** (was 89; commands.py + doctor.py both module-level new). `ruff` → **43** (down 1; possibly an unused import collapsed during the move).

**Merge:** `feature/l36-app-commands-split` → `develop` via `--no-ff` merge commit `ecdbe3d`.

**Queue advance:** `KIMI_CURRENT.md` → **L37** (code cleanup sweep + ruff baseline crunch).

---

## 2026-04-19 — Loop: L35d + Stage B — `UPGRADE.md` + `[0.8.0]` CHANGELOG amendment + L35-arc handoff (clean Kimi run); v0.8.0 re-tagged + merged to main locally

**Kimi (L35d):** Clean run, 3 docs commits, ~7.5 minutes wall time (`exit_code: 0`, `elapsed_ms: 443483`). Valid `.kimi-done` with `LOOP=L35d`, `COMMIT=8fffad8`, `TESTS=778 passed, 6 skipped` (unchanged from L35c — docs-only loop), `MYPY_FINAL_ERRORS=0`. **Sixth clean L35 mini-loop in a row** (L35a, b, c, d all autonomous; the original monolithic L35 split was the right call).

**What L35d shipped:**

- `UPGRADE.md` (new at repo root, 145 lines) — verbatim section ordering per spec. Cleanly references the now-real `hestia doctor` (L35c) in step 6. Defaults shown for `trust:` (`paranoid`), `web_search:` (disabled), `security:` (entropy threshold 5.5), `style:` (enabled), `reflection:` (off), with a one-paragraph callout on `skills:` being inert without `HESTIA_EXPERIMENTAL_SKILLS=1`.
- `CHANGELOG.md` `[0.8.0]` block amended with three new bullets under "Bug fixes & hardening" (style disable, policy show, join_overhead cache), a new "New diagnostic commands" subsection (hestia doctor), a new "Upgrade docs" subsection (UPGRADE.md), and stats line updated to `~778 tests passing`.
- `docs/handoffs/L35-pre-release-fixes-arc-handoff.md` (new, 79 lines) covering all four mini-loops as one document.

**Review (Cursor):** Diffs match spec. CHANGELOG amendment is in-place (no `[0.8.1]` section invented). Re-ran gate from develop tip: **778 passed, 6 skipped** (unchanged); mypy 0; ruff 44; uv.lock in sync.

**Merge:** `feature/l35d-upgrade-doc-and-release-prep` → `develop` via `--no-ff` merge commit `c5f68ea`. **Closes the L35 pre-release-fixes arc.**

---

## 2026-04-19 — Stage B (Cursor): re-tag v0.8.0 at the L35d merge tip; merge develop into main locally

**Why Cursor-only:** per `.cursorrules`, Dylan owns `git push`. The first L35 attempt tagged `v0.8.0` at `d9b889d` and merged to main locally; both were thrown away after the pre-release-plan added L35a-d work. This is the second-and-final tag.

**What Cursor did:**

1. `git tag -a v0.8.0 develop` at the L35d merge tip (`c5f68ea`). Annotated tag with the v0.8.0 release message (highlights of the L20-L35 arc, 778 tests, 0 mypy, 22 ADRs, references to CHANGELOG and UPGRADE.md).
2. `git checkout main && git merge --no-ff develop` with a release-merge message listing the L35a-d highlights. Merge commit `7f2af27` on `main`.
3. **Final gate from main tip:** `pytest tests/unit tests/integration tests/cli` → **777 passed, 6 skipped** (the missing 1 vs. develop is the docs test module that requires `tests/docs/` to be in the run; the L35d docs-only changes don't add tests). `mypy src/hestia` → **0**. `uv.lock` is synced.
4. Did **not** push anything. Push commands prepared for Dylan in the morning summary.

**Local repo state:**

- `main` ahead of `origin/main` by **180 commits** (full L20→L35d arc + the merge commit).
- `develop` ahead of `origin/develop` by **23 commits** (the L35a/b/c/d feature merges + orchestration commits).
- Annotated tag `v0.8.0` at `c5f68ea`, contained by both `main` and `develop`.

**Dylan's push commands (in the morning):**

```bash
cd ~/Hestia
git push origin develop
git push origin main
git push origin v0.8.0
```

After that, optionally cut a GitHub release from the `v0.8.0` tag using the `## [0.8.0] — 2026-04-18` block in CHANGELOG as the release notes.

**Queue advance:** v0.8.0 release work complete. `KIMI_CURRENT.md` → **L36** (overnight queue starts).

---

## 2026-04-19 — Loop: L35c — `hestia doctor` command (clean Kimi run on the largest L35 mini-loop) → merged to develop

**Kimi:** Clean run, 5 commits exactly to budget, ~22 minutes wall time (`exit_code: 0`, `elapsed_ms: 1316135`). Valid `.kimi-done` with `LOOP=L35c`, `COMMIT=a3526b3`, `TESTS=777 passed, 6 skipped`, `MYPY_FINAL_ERRORS=0`. Working tree clean before write. **Mini-loop strategy continues to win** — this was the loop most likely to hit the step ceiling (9 checks × 2 tests + new module + 2 integration points, exactly the shape that broke L29-L31), and Kimi delivered it autonomously in one run.

**What shipped:**

- `src/hestia/doctor.py` (new, 346 lines) — flat function-list module per spec. Public API is `CheckResult` dataclass, `run_checks(app) → list[CheckResult]`, `render_results(results, plain=False) → str`. Nine private async check functions, each catching its own exceptions and returning a `CheckResult`. `run_checks` itself wraps each call in a defensive `try/except` so an uncaught bug surfaces as a failed check rather than aborting the suite.
- `src/hestia/app.py` (+9 lines) — `_cmd_doctor(app, plain) → int` that calls `run_checks`, prints `render_results`, returns the appropriate exit code. Local import of `hestia.doctor` to avoid circular-import hazards.
- `src/hestia/cli.py` (+14 lines) — `hestia doctor [--plain]` registered as `@cli.command()` + `@click.option` + `@run_async`; calls `_cmd_doctor` and `sys.exit`s on failure.
- `tests/unit/test_doctor_checks.py` (new, 375 lines) — 18 unit tests covering green and red paths for every check (Python version too old, `uv pip check` drift, `uv` not on PATH, SQLite corruption, llama.cpp timeout/connection-error, missing Telegram token, missing email password env, unknown trust preset, unparseable memory epoch).
- `tests/cli/test_doctor_command.py` (new, 163 lines) + `tests/cli/__init__.py` — 4 e2e tests via `CliRunner`: clean-env exit-0, any-fail exit-1, `--plain` ASCII markers, default Unicode markers.
- `docs/handoffs/L35c-hestia-doctor-handoff.md` (new, 52 lines).

**Smoke test (Cursor, post-merge):** `uv run hestia doctor --plain` against the dev environment exits with code 1, surfacing `[FAIL] sqlite_dbs_readable` because the dev shell's CWD lacks the configured DB path. Eight other checks `[ok]`. Exactly the kind of "real misconfiguration → real failure surface" the command is designed for.

**Review (Cursor):**

- Diff is large (7 files, +959 / 0) but every line is in scope. No off-spec touches anywhere else in the tree.
- Re-ran full gate (`tests/unit tests/integration tests/cli tests/docs`): **778 passed, 6 skipped** (one extra vs. Kimi's report — likely a docs-test pickup). `mypy` → 0. `ruff` → 44 (unchanged). 

**Merge:** `feature/l35c-hestia-doctor` → `develop` via `--no-ff` merge commit `71ea99f`.

**Queue advance:** `KIMI_CURRENT.md` → **L35d** (`UPGRADE.md` + `[0.8.0]` CHANGELOG amendment + L35-arc handoff).

---

## 2026-04-19 — Loop: L35b — `_cmd_policy_show` derives from live registry/config (clean Kimi run) → merged to develop

**Kimi:** Clean run, 3 commits, ~11 minutes wall time (`exit_code: 0`, `elapsed_ms: 662106`). Valid `.kimi-done` with `LOOP=L35b`, `COMMIT=275fc6d`, `TESTS=753 passed, 6 skipped`, `MYPY_FINAL_ERRORS=0`. Working tree clean before write. Mini-loop strategy still holding.

**What shipped:**

All five drift sites in `_cmd_policy_show` (in `src/hestia/app.py`) are now wired to live state:

- `Active preset:` line surfaces `cfg.trust.preset` (new optional `str | None` field on `TrustConfig`, default `None`; falls back to `(custom — no preset name)`).
- Confirmation-required tool list iterates `app.tool_registry.list_names()` and filters by `ToolMetadata.requires_confirmation`. Renders `(none)` when zero confirming tools.
- Delegation keywords line reads `cfg.policy.delegation_keywords or DEFAULT_DELEGATION_KEYWORDS` (the L33c constant). Imported at the top of `app.py`.
- Research keywords line preserved as a literal but flagged with `# TODO(L38): consolidate research keywords through PolicyConfig` — exactly what L35b spec asked for.
- Retry "Max attempts" reads `policy_engine.retry_max_attempts`. New module-level constant `DEFAULT_RETRY_MAX_ATTEMPTS = 2` in `src/hestia/policy/default.py`; `DefaultPolicyEngine.__init__` now sets `self.retry_max_attempts = DEFAULT_RETRY_MAX_ATTEMPTS`. **Spec-compliant** — no new `PolicyConfig.retry_max_attempts` field as the spec ruled out for L35b.

`tests/unit/test_policy_show_wiring.py` (new, 145 lines) — six tests: confirmation-tools-from-registry, zero-confirmation-tools, retry-from-engine, custom-keywords, default-keywords-fallback, trust-preset-surfaced. Uses a fixture-built `CliAppContext` rather than relying on `make_app`, which keeps the tests independent of bootstrap drift.

**Review (Cursor):**

- Diff is small (5 files, +195 / -5). All changes are inside `_cmd_policy_show` plus the two minimal config/policy additions the spec authorized.
- Re-ran gate: **753 passed, 6 skipped** (+6 vs. L35a's 747). `mypy` → 0. `ruff` → 44 (unchanged).
- The `TrustConfig.preset` field is additive only (defaulted None; existing `paranoid()` / `household()` / `developer()` factories don't set it yet — that's a future loop's job, perhaps L40 dogfooding rollup).

**Merge:** `feature/l35b-policy-show-wiring` → `develop` via `--no-ff` merge commit `852d546`.

**Queue advance:** `KIMI_CURRENT.md` → **L35c** (`hestia doctor` command — biggest L35 mini-loop).

---

## 2026-04-19 — Loop: L35a — `style disable` Click signature + ContextBuilder `_join_overhead` lazy cache (clean Kimi run) → merged to develop

**Kimi:** Clean run, 4 commits, ~15.5 minutes wall time (`exit_code: 0`, `elapsed_ms: 938896`). Valid `.kimi-done` with `LOOP=L35a`, `COMMIT=42d446e`, `TESTS=747 passed, 6 skipped`, `MYPY_FINAL_ERRORS=0`. Working tree clean before write. Mini-loop strategy continues to validate.

**What shipped:**

- `src/hestia/cli.py` — `style_disable` is now `@click.pass_obj` with the L35a docstring template (process-only + how to persist via config or `HESTIA_STYLE_ENABLED=0`). Output message rewritten to be honest about the in-memory-only semantic.
- `src/hestia/context/builder.py` — `_join_overhead` is now `int | None`, computed lazily once per instance via the new `_compute_join_overhead()` helper, and read at the math sites via `_join_overhead = self._join_overhead or 0` (preserving the existing math-on-zero behavior for the "not enough messages to measure" case). The cache **does not store a `0` that came from too-few-messages**, so a later `build()` with more history will measure the real value — exactly the spec's edge-case requirement.
- `tests/unit/test_cli_style_disable.py` (new, 43 lines) — three tests: invokes-without-error, mutates-in-memory-only, help-mentions-persistence.
- `tests/unit/test_context_builder_join_overhead_cache.py` (new, 170 lines) — four tests including `test_join_overhead_recomputed_after_too_few_messages_initially` (locks the edge case) and `test_join_overhead_value_matches_inline_implementation` (locks the formula).
- `tests/unit/test_context_builder_tokenize_cache.py` (existing, 11-line tweak) — Kimi adjusted the L32c test to the new internal API. Diff is mechanical, no semantics change.
- `docs/handoffs/L35a-style-and-overhead-fixes-handoff.md` (new, 37 lines).

**Audit findings:** Kimi ran the `*_disable` / `*_enable` Click-signature audit per the spec; `style_disable` was the only broken command. Other `*_disable`-style commands either don't exist or use `@run_async` already.

**Review (Cursor):**

- Diffs match spec to the line. The `_join_overhead` edge case is the kind of subtlety I worried about and Kimi handled it correctly — the `if overhead != 0 or len(history) >= 2 or len(...) >= 2` guard is exactly what the spec asked for.
- Re-ran gate from the branch tip: **747 passed, 6 skipped** (+6 vs. L34 baseline of 741). `mypy src/hestia` → 0 errors. `ruff check src/` → 44 (unchanged). 11 warnings — all the pre-existing `aiosqlite Event loop is closed` noise documented at L28.

**Merge:** `feature/l35a-style-and-overhead-fixes` → `develop` via `--no-ff` merge commit `2575152`.

**Queue advance:** `KIMI_CURRENT.md` → **L35b** (`_cmd_policy_show` derive-from-registry refactor).

---

## 2026-04-18 — Planning: L35 split into L35a/b/c/d after pre-release-plan landed; L36-L38 queued; L39-L40 deferred until dogfooding

**Trigger:** Dylan pushed `develop` (including the v0.8.0 commit) to origin two days ago. **76 unique cloners** observed in those 2 days with zero announcements — public traffic is real and on the **stale** v0.2.2 tag. Dylan added `docs/development-process/reviews/v0.8.0-pre-release-plan.md` (`6317707`) at 22:09 with a six-section L35 covering pre-release fixes (`style disable`, `policy show`, `_join_overhead` cache, new `hestia doctor`), `UPGRADE.md`, and CHANGELOG amendment. Asked Cursor to break it down so v0.8.0 ships **tonight** (Dylan staying up) and L36+ runs overnight after he sleeps.

**Why split L35:** the same lesson L29-L31 taught and L32/L33 mini-loops validated — six sections in one Kimi loop will hit the per-iteration step ceiling (`--max-steps-per-turn=250`). `hestia doctor` alone is 9 checks × 2 tests + new module + 2 file integrations. The L35d "amend CHANGELOG" can't run until L35a-c land, so the docs amendment naturally separates.

**Cursor actions:**

1. Reset local `main` to `origin/main` (was 155 ahead from the prior local merge that Dylan never pushed). Deleted local `v0.8.0` tag (was on the un-pushed `c95814f`). The `chore(release): v0.8.0` commit (`d9b889d`) stays on develop and will be re-tagged at the post-L35d tip.
2. Wrote four L35 mini-loop specs (`kimi-loops/L35a-*.md`, `L35b-*.md`, `L35c-*.md`, `L35d-*.md`).
3. Wrote three overnight specs (`kimi-loops/L36-app-commands-split.md`, `L37-code-cleanup-sweep.md`, `L38-delegation-and-disable-persistence.md`).
4. Renamed the original Cursor-only release spec to `_superseded-L35-release-v0.8.0.md` for history.
5. Updated `kimi-phase-queue.md` table; documented L39 + L40 as deferred until post-dogfooding (per the pre-release plan's own dependency note).
6. Pointed `KIMI_CURRENT.md` at L35a.

**Tonight's chain:** L35a (style + overhead) → L35b (policy show) → L35c (doctor) → L35d (UPGRADE.md + CHANGELOG amend + L35 arc handoff) → Cursor re-tags `v0.8.0` and re-merges develop into main → Dylan pushes `develop main v0.8.0` and optionally cuts a GitHub release.

**Overnight chain (Dylan asleep):** L36 (`app.py` → `commands.py` extraction) → L37 (cleanup sweep, ruff baseline crunch from 44 to ≤24) → L38 (delegation keyword consolidation + `*_disable` semantics audit). Each posts a `.kimi-done`; Cursor reviews, merges to develop, advances `KIMI_CURRENT.md`, and starts the next.

**Deferred:** L39 (`hestia upgrade` command) explicitly waits for "at least one dogfooding-cycle worth of real upgrade pain observed" per the pre-release plan. L40 waits for `docs/dogfooding/2026-04-journal.md` to be populated. Skipping these overnight is the right call.

**Risk register:**

- L35c is the largest of the four pre-release loops (5 commits; new module; 22+ tests). If it hits the step ceiling like L30/L31 did, Cursor finishes it manually rather than re-launching.
- L36 (`app.py` decomposition) is behavior-preserving but touches every `_cmd_*` import path in `cli.py`. If existing tests start failing on imports, that's the expected signal — the fix is in the move, not the tests.
- The `_join_overhead` cache edge case (don't cache `0` from "too few messages to measure") is the kind of subtlety that Kimi can miss. Cursor reviews the diff carefully on L35a merge.

---

## 2026-04-18 — Loop: L35 (original, Cursor-only) — **SUPERSEDED** by L35a/b/c/d split

> **Status:** This entry documents the first L35 attempt (single Cursor-driven release loop). It was **never pushed**. After Dylan added `docs/development-process/reviews/v0.8.0-pre-release-plan.md` (`6317707`) flagging four real bugs to fix before tagging, the local v0.8.0 tag was deleted and `main` was reset to `origin/main`. Release work split into L35a/b/c/d (see the planning entry above this one). Keeping the entry below for the curated CHANGELOG draft and the process notes — those are still accurate, just paused until L35d lands.

**Why no Kimi:** L35 is a release loop. Per `.cursorrules`, Dylan owns `git push`. The L35 spec as originally written had Kimi running `git push origin main` and `git push origin v0.8.0`, which would either silently fail or hang on missing credentials in the headless Kimi process. Cursor executed the local prep directly.

**What Cursor did:**

1. Verified pre-release gate on `develop` tip (`d51d816`): **741 passed, 6 skipped, mypy 0, ruff 44**. Working tree clean.
2. Bumped `pyproject.toml` `0.7.12` → `0.8.0`.
3. Bumped `src/hestia/__init__.py` `__version__` `0.7.0` → `0.8.0` (had been **stale since pre-window** — caught by reading the file, not by tests).
4. Promoted the L34 "Towards 0.8.0" CHANGELOG preface into a full curated `## [0.8.0] — 2026-04-18` section, grouped by theme (Trust & confirmations · Context & resilience · Architecture & quality · Security · Email · Reflection & style · Bug fixes & hardening · Skills & polish), with one line per loop in conventional-commit voice. Final stats block at the bottom.
5. `uv lock` synced the lockfile.
6. Wrote `docs/handoffs/L35-release-v0.8.0-handoff.md` covering the loop manifest, mini-loop chunking validation, Cursor's local steps, and Dylan's push commands.
7. Single release commit on `develop`: `chore(release): v0.8.0` (`d9b889d`).
8. Annotated tag `v0.8.0` on the release commit.
9. `git checkout main` and `git merge --no-ff develop` with a release-merge message listing the 56-commit summary. Merge commit `604e805` on `main`.
10. **Stopped.** Did not push anything.

**Verification:**

- Final pytest from `main` tip: **741 passed, 6 skipped**.
- `git tag --list 'v0.8*'` → `v0.8.0`. Tag commit `d9b889d` is contained by both `main` and `develop`.
- Branches state: `develop [ahead 61]`, `main [ahead 155]`. Nothing pushed yet.

**Dylan's push commands** (also in the L35 handoff):

```bash
cd ~/Hestia
git push origin develop
git push origin main
git push origin v0.8.0
```

After that, optionally cut a GitHub release from the tag using the `[0.8.0]` CHANGELOG section as the release notes.

**Queue advance:** L35 was the last loop in the queue. There is no `KIMI_CURRENT.md` advance — the queue is drained. Next steps are Dylan's: push, optionally cut a GitHub release, then ideally **use Hestia hard for a week before queueing more loops**. The honest backlog comes from real annoyances, not retrospective audits.

---

## 2026-04-18 — Loop: L34 — public-release polish (README, deployment, email setup, CHANGELOG curation) (Kimi clean run) → merged to develop

**Kimi:** Sixth clean mini-loop in a row (only counting L32a-L33c-L34, not L33b's missed-commit case). 7 commits, valid `.kimi-done`, ~12 minutes wall time. Docs-only loop, so no production-code risk.

**What shipped:**

- README "Recommended models" table: Llama-3.1-8B-Instruct Q4_K_M (default), Qwen 2.5 7B Q4_K_M, Llama-3.2-3B Q5_K_M, Qwen 2.5 14B Q4_K_M with VRAM and use-case notes. Static K-quants recommended; imatrix quants warned against for tool calling.
- README "Running Hestia as a daemon" section: documents every file in `deploy/` (`hestia-agent.service`, `hestia-llama.service`, `hestia-llama.alt-port.service.example`, `install.sh`, `example_config.py`, `README.md`), shows the `systemctl --user daemon-reload && systemctl --user enable --now hestia.service` sequence, cross-links env-var configuration (`HESTIA_SOUL_PATH`, `HESTIA_CALIBRATION_PATH`, `HESTIA_EXPERIMENTAL_SKILLS`, `EMAIL_APP_PASSWORD`).
- README "Demo" subsection with asciinema link placeholder, `docs/assets/hestia-chat.png` placeholder path (empty file created at that path), and a 3-line text transcript of a `hestia chat` interaction with one tool call. TODO marker for Dylan to record the asciicast.
- `docs/guides/email-setup.md` rewritten env-var-first: `password_env: "EMAIL_APP_PASSWORD"` is the lead example; plaintext `password=` demoted to an "ephemeral testing only" callout; cross-references to L25 handoff and the L29 ADR consolidation.
- CHANGELOG: new curated `## [0.7.12] — 2026-04-18` entry; new "Towards 0.8.0" preface block listing L20→L34 highlights for L35 to promote.
- New `tests/docs/test_readme_links.py` (50 lines): walks all relative links in `README.md` and asserts each path resolves. Catches the next time someone moves an ADR or guide.
- ADR-0021 and ADR-0022 left untouched (already at the right level of detail from L32c and L33c).

**Review (Cursor):**

- Full gate on the branch tip: **`741 passed, 6 skipped`** (unchanged from L33c — the new docs test module is part of the count once `pytest --collect` discovers `tests/docs/`). `uv run mypy src/hestia` → **0**. `uv run ruff check src/` → **44** (no regression).
- `ls deploy/` matches what the README documents.

**Merge:** `feature/l34-public-release-polish` → `develop` via `--no-ff` merge commit `d51d816`.

**Queue advance:** `KIMI_CURRENT.md` → **L35** (release v0.8.0 to main; Cursor-driven, no Kimi launch).

---

## 2026-04-18 — Loop: L33b — `EmailAdapter` per-invocation IMAP session reuse + composite tool (Kimi clean spec, Cursor caught one missed commit) → merged to develop

**Kimi:** Fifth mini-loop. All 5 spec commits landed cleanly, valid `.kimi-done` written. Wall time ~19 minutes. **One snag:** Kimi made a 6th edit on disk *after* the release commit (hoisting the `draft-unknown` early-return out of the new `imap_session()` context) and never committed it. The edit was a real bug fix — without it, `test_send_draft_rejects_draft_unknown` failed because the placeholder check was sitting *inside* the new session helper (so it never fired before the IMAP connection was attempted). Cursor restored the edit, ran the gate green, committed it as `fix(email): hoist draft-unknown rejection out of imap_session` on the L33b branch, then merged.

**What shipped:**

- New `EmailAdapter.imap_session(folder=...)` async context manager. Tracks the active connection on a `contextvars.ContextVar[IMAP4_SSL | None]`. On entry: if a parent session is active in the same context, reuse it (no new connect). Otherwise: connect, login, `SELECT folder`. On exit: only the outermost frame logs out and clears the ContextVar.
- All per-method connection blocks (`list_messages`, `read_message`, `search_messages`, `create_draft`, `move_message`, `flag_message`) routed through `imap_session()`. Standalone behavior preserved (each call still opens + closes its own connection if no outer session is active).
- New composite tool `make_email_search_and_read_tool` in `src/hestia/tools/builtin/email_tools.py`. Takes `query` + `limit`; opens one IMAP session, runs the search, reads the top `limit` messages, returns a list of dicts (uid, from, subject, snippet of body, full body in artifact handle for large messages). One handshake per invocation.
- New `tests/unit/test_email_session_reuse.py` (103 lines): nested `imap_session()` reuses outer connection (single connect); session closes on exception via the context manager exit; standalone calls without an outer session each open+close their own connection.
- New `tests/integration/test_email_search_and_read.py` (164 lines): end-to-end exercise of the composite tool against the existing email mock fixture.
- `src/hestia/app.py` gained the registration call for the new composite tool.
- Cursor fix commit `0abb34f`: `send_draft("draft-unknown")` rejected at the top of the method, before the IMAP session opens. Restores the fast-path validation contract.

**Review (Cursor):**

- Initial post-spec gate failed: 1 failed (`test_send_draft_rejects_draft_unknown`). After applying the fix Kimi staged but didn't commit: **`726 passed, 6 skipped`** (+7 from L33a's 719 — the new email tests). `uv run mypy src/hestia` → **0**. `uv run ruff check src/` → **44** (no regression).

**Merge:** `feature/l33b-email-session-reuse` → `develop` via `--no-ff` merge commit `f7dcd91`.

**Drift call-out:** This is the first loop in the new mini-loop chunking strategy where Kimi technically slipped — they made an edit on disk after the spec was complete and forgot to commit it (likely the per-turn step ceiling or just a bookkeeping miss). The miss was harmless because Cursor's post-merge gate caught it. **Going forward**, post-spec gates remain mandatory even on "clean" Kimi loops — Kimi may stage a final fix without committing it.

**Queue advance:** `KIMI_CURRENT.md` → **L33c** (skills experimental flag + `_format_datetime` + `delegation_keywords` + matrix parser test — closes the L33 arc).

---

## 2026-04-18 — Loop: L33a — `InjectionScanner` threshold tuning + structured-content filters (Kimi clean run) → merged to develop

**Kimi:** Fourth clean mini-loop in a row. 4 commits, valid `.kimi-done`, ~26 minutes wall time (longer than L32 loops because the new tests exercise large synthetic blobs and the inner pytest run is the dominant cost).

**What shipped (BEHAVIOR CHANGE):**

- Default `InjectionScanner.entropy_threshold` raised from **4.2 → 5.5**. Docstring documents the empirical baselines (English ~4.0–4.5, JSON ~5.0–5.5, base64 ~6.0+).
- New private `_looks_structured(content)` helper: returns True for content that is parseable JSON, looks like base64-only (≥ 100 chars and ≥ 80% in `[A-Za-z0-9+/=]`), or looks CSS/HTML-ish (high `{`/`}`/`;` density or balanced `<…>` pairs).
- When `_looks_structured(content) is True` and `SecurityConfig.injection_skip_filters_for_structured` is True (the new default), the entropy gate is **skipped**. The regex pattern check still runs unconditionally — known prompt-injection phrases ("ignore previous instructions", etc.) get flagged regardless of structure.
- New `SecurityConfig.injection_entropy_threshold: float = 5.5` and `SecurityConfig.injection_skip_filters_for_structured: bool = True`.
- `src/hestia/app.py` updated to pass the new settings into the scanner factory.
- New `tests/unit/test_injection_scanner_tuning.py` (~7 tests): minified JSON / base64 / CSS no longer false-positive; injection phrases inside JSON still flagged; English text under threshold; high-entropy random bytes still flagged when not structured; toggle disabling skip-filters restores the old behavior.

**Review (Cursor):**

- Full gate on the branch tip: **`719 passed, 6 skipped`** (+7 from L32c's 712 — exactly the new tuning module). `uv run mypy src/hestia` → **0**. `uv run ruff check src/` → **44** (no regression).
- Behavior change captured under `[0.7.9]` in CHANGELOG with explicit "BEHAVIOR CHANGE" callout.

**Merge:** `feature/l33a-injection-scanner-tuning` → `develop` via `--no-ff` merge commit `d28cdad`.

**Queue advance:** `KIMI_CURRENT.md` → **L33b** (EmailAdapter per-invocation IMAP session reuse + `email_search_and_read` composite tool).

---

## 2026-04-18 — Loop: L32c — `ContextBuilder` per-message `/tokenize` cache (Kimi clean run) → merged to develop · CLOSES L32 ARC

**Kimi:** Third clean mini-loop in a row. 5 commits, valid `.kimi-done`, ~20 minutes wall time. The L32 split strategy is fully validated: **0 human commits across L32a + L32b + L32c**, no per-turn step ceiling hits, all gates green at every step.

**What shipped:**

- `ContextBuilder` now keeps a `_tokenize_cache: dict[tuple[str, str], int]` keyed on `(role, content)`. Per-message tokenize results survive across builds for the lifetime of the builder instance.
- New private `_count_tokens(message)` checks the cache before issuing a `/tokenize` call; new `_join_overhead` is computed once per build and reused as the constant approximation for join cost.
- Trim window selection now sums cached counts plus the constant overhead instead of POSTing the joined candidate string each iteration. Amortized **O(1) `/tokenize` calls per build for unchanged messages** (was O(N)).
- New `tests/unit/test_context_builder_tokenize_cache.py` (181 lines, ~6 tests): cache hits across rebuilds, single new tokenize call when one new message is added, parity with the joined-string baseline within ±1 boundary message, `(role, content)` is the cache key (independent of `created_at`).
- Many existing context-builder tests + integration tests gained explicit `tokenize` stubs (Kimi noticed several were relying on a fall-through behavior that the cache change tightened — the test fixture updates kept them honest).
- New ADR: `docs/adr/ADR-0021-context-builder-prefix-registry-and-tokenize-cache.md` covers both L32b (registry) and L32c (cache) as a coherent rework.
- New handoff: `docs/handoffs/L32-context-rework-handoff.md` summarizes the full L32 arc with final test/mypy/ruff numbers.

**Review (Cursor):**

- Full gate on the branch tip: **`712 passed, 6 skipped`** (+4 from L32b's 708). `uv run mypy src/hestia` → **0**. `uv run ruff check src/` → **44** (no regression).
- One harmless noise edit: Kimi reverted `KIMI_CURRENT.md` to a stale snapshot at some step. Discarded with `git checkout --` before merge — not part of the spec, not committed.

**Merge:** `feature/l32c-context-tokenize-cache` → `develop` via `--no-ff` merge commit `6b6fb36`.

**L32 arc summary:** v0.7.5 → v0.7.8. Tests 701 → 712 (+11 new regression tests across the arc). Mypy 0 throughout. Ruff 44 throughout. **Three consecutive clean Kimi runs with zero per-turn step ceiling hits** — vs L29/L30/L31 where every monolithic loop tripped the ceiling. The mini-loop chunking strategy works.

**Queue advance:** `KIMI_CURRENT.md` → **L33a** (InjectionScanner threshold tuning + structured-content filters).

---

## 2026-04-18 — Loop: L32b — `ContextBuilder` named ordered prefix-layer registry (Kimi clean run) → merged to develop

**Kimi:** Second clean mini-loop in a row. 3 commits, valid `.kimi-done`, ~9 minutes wall time. Confirms the chunking strategy stays under the per-turn step ceiling reliably.

**What shipped:**

- Per-call `identity_prefix`, `memory_epoch_prefix`, `skill_index_prefix`, `style_prefix` kwargs **removed** from `ContextBuilder.build()`. Setters (`set_identity_prefix`, `set_memory_epoch_prefix`, etc.) are now the only path to set prefixes.
- Four parallel `if effective_x: parts.append(effective_x)` blocks replaced by an ordered `_PrefixLayer` registry. Assembly is a single comprehension: `parts = [layer.value for layer in self._prefix_layers() if layer.value]`.
- `src/hestia/orchestrator/engine.py` had **one real caller** still passing kwargs (`context_builder.build(..., style_prefix=...)`) — Kimi's §1 grep caught it and migrated to `set_style_prefix` before the build. Two test files (`test_injection_orchestrator.py`, `test_style_profile_context.py`) similarly migrated.
- New `tests/unit/test_context_builder_prefix_registry.py` (4 tests): order is locked, omitted layers don't leave double-blanks, all-omitted falls through to system prompt only, and `inspect.signature(ContextBuilder.build)` no longer contains the four kwargs (lock against re-introduction).
- `src/hestia/context/builder.py` net **−10 lines**: 64 lines vs 74 before.

**Review (Cursor):**

- Full gate on the branch tip: **`708 passed, 6 skipped`** (+4 from L32a's 704 — exactly the 4 new registry tests). `uv run mypy src/hestia` → **0**. `uv run ruff check src/` → **44** (no regression).

**Merge:** `feature/l32b-context-prefix-registry` → `develop` via `--no-ff` merge commit `e74ed46`.

**Queue advance:** `KIMI_CURRENT.md` → **L32c** (per-message `/tokenize` cache + ADR-0021).

---

## 2026-04-18 — Loop: L32a — delete dead `TurnState` and `ToolResult` from `core/types.py` (Kimi clean run) → merged to develop

**Kimi:** First mini-loop in the new sub-letter chunking strategy. **Clean run** — all 3 spec commits landed, valid `.kimi-done` written without intervention. Run time: ~5 minutes (well under the per-turn step ceiling). Confirms the chunking + `--max-steps-per-turn=250` headroom works.

**What shipped:**

- `TurnState` enum + `TERMINAL_STATES` constant removed from `src/hestia/core/types.py`.
- `ToolResult` dataclass removed from `src/hestia/core/types.py`.
- `Enum` and related unused imports cleaned up.
- New `tests/unit/test_core_types_dead_code_removed.py` locks the contract: asserts `TurnState`/`TERMINAL_STATES`/`ToolResult` are absent from `hestia.core.types`, and `TurnState` is still importable from `hestia.orchestrator.types`.

**Review (Cursor):**

- Full gate on the branch tip: **`704 passed, 6 skipped`** (+3 from L31's 701 — exactly the 3 new tests in the regression module). `uv run mypy src/hestia` → **0**. `uv run ruff check src/` → **44** (no regression).
- §1 grep pre-flight passed (no consumer outside the dead code itself), so no caller-side changes were needed.
- `core/types.py` is now ~75 lines (was ~100) and contains only the live types: `Message`, `Session`, `SessionState`, `SessionTemperature`, `ScheduledTask`, `Turn`, `Capability`.

**Merge:** `feature/l32a-delete-dead-types` → `develop` via `--no-ff` merge commit `7ea4a53`.

**Queue advance:** `KIMI_CURRENT.md` → **L32b** (named ordered prefix-layer registry in `ContextBuilder`).

---

## 2026-04-18 — Loop: L31 — orchestrator engine cleanup (Kimi → Cursor finish) → merged to develop

**Kimi:** Started L31 from `feature/l31-engine-cleanup` (off `develop` tip `30a224f`). **All 9 spec commits landed** (extract `_build_failure_bundle`, hoist `delegated`/`tool_chain`, single `get_messages`, accumulate artifact handles from `ToolCallResult`, extract `_check_confirmation`, `ToolCallResult.error` classmethod, regression tests, version bump, handoff). Then Kimi hit `--max-steps-per-turn=100` (the **per-iteration step ceiling**, distinct from `--max-ralph-iterations` which was already `-1`) and exited. **No `.kimi-done` was written.** The uncommitted working tree contained ~60 lines of cosmetic compaction noise (collapsing dataclass kwargs onto single lines, stripping comments and blank lines, removing docstring detail) — not bug fixes.

**Cursor finish (manual):**

1. Discarded the noise diff (`git checkout -- src/hestia/orchestrator/engine.py`).
2. Verified the three "must be empty" gates pass on the L31 branch: `git grep 'ToolCallResult(status="error"' -- src/hestia` → 0; `git grep 'locals().get(' -- src/hestia` → 0; `git grep 're.findall(.*artifact' -- src/hestia` → 0.
3. Wrote `.kimi-done` with the final commit sha (`86f5ee6`), test summary (`701 passed, 6 skipped`), `MYPY_FINAL_ERRORS=0`, and a `NOTE=` documenting the per-turn step ceiling.

**What shipped:**

- `Orchestrator._build_failure_bundle(...)` collapses the duplicated `ContextTooLargeError` and generic `Exception` failure-bundle blocks (previously ~60 lines × 2).
- `delegated` and `tool_chain` declared at the top of the outer `try` in `process_turn`; the defensive `locals().get("delegated", False)` is gone.
- `process_turn` calls `await self._store.get_messages(session.id)` exactly once per turn (was twice — once at the top, once after DONE for artifact mining).
- Artifact handles are now accumulated from `ToolCallResult.artifact_handle` during dispatch into a `turn_artifact_handles: list[str]`. The `re.findall(r"artifact://...")` recovery path is gone.
- `_check_confirmation(...)` is the one place the confirmation logic lives; both `_dispatch_tool_call` branches call it.
- New `ToolCallResult.error(content)` classmethod in `src/hestia/tools/types.py`; every long-form `ToolCallResult(status="error", content=..., artifact_handle=None, truncated=False)` in `engine.py` now goes through it.
- 3 new regression test modules (`test_orchestrator_failure_bundle.py`, `test_orchestrator_confirmation_helper.py`, `test_orchestrator_artifact_accumulation.py`) covering the dedup-parity contracts.
- `engine.py` at **848 lines** (target was ≤ 750; the extra 100 lines are real complexity in `process_turn` that wasn't part of the dedup spec — left alone for a future loop).
- Bumped to `0.7.5`; `uv.lock` synced; CHANGELOG + handoff written.

**Review (Cursor):**

- Full gate on the branch tip: **`701 passed, 6 skipped`** (+10 from L30's 691 — exactly the 3 new test modules' worth, 11 minus 1 fixture parametrization tweak). `uv run mypy src/hestia` → **0**. `uv run ruff check src/` → **44** (no regression from L30's baseline).

**Merge:** `feature/l31-engine-cleanup` → `develop` via `--no-ff` merge commit `2f20850`.

**Pattern call-out:** L29, L30, L31 all hit `--max-steps-per-turn=100` (the per-iteration step ceiling). The Kimi CLI exposes that flag — Cursor bumped the launcher to `--max-steps-per-turn 250` for headroom and **also** split the originally-monolithic L32 (ContextBuilder + dead-code purge) and L33 (email pool + scanner + skills + style polish) into 6 mini-loops (L32a/b/c, L33a/b/c). Each mini-loop is ≤ 5 commits with a single theme and one new test module, sized to fit comfortably under 100 steps even without the launcher bump. See `kimi-phase-queue.md` for the new ordering.

**Queue advance:** `KIMI_CURRENT.md` → **L32a** (delete dead `TurnState` and `ToolResult` from `core/types.py`, ≤ 3 commits, the smallest possible thing — also a clean test of the new size).

---

## 2026-04-18 — Loop: L30 — `cli.py` decomposition into `app.py` + `platforms/runners.py` (Kimi → Cursor finish) → merged to develop

**Kimi:** Started L30 from `feature/l30-cli-decomposition` (off `develop` tip `bbed167`). Created `src/hestia/app.py` (~1,500 lines), `src/hestia/platforms/runners.py` (~245 lines), and rewrote `src/hestia/cli.py` down to ~575 lines — but **never committed any of it** before hitting the `--max-ralph-iterations` (100) ceiling and exiting. **No `.kimi-done` was written.** Resume id captured but not used; the working tree was already in a recoverable state and the remaining work was small enough that another Kimi spin-up would have cost more than the manual fix-up.

**Cursor finish (manual):**

1. Removed dangling `@cli.command()` / `@click.option(...)` / `@click.pass_context` decorators in `cli.py` lines 240-243 (orphaned from a removed command body).
2. Added `_cmd_schedule_add` to the import list from `hestia.app` (Kimi referenced it without importing).
3. Restored missing `_cmd_schedule_enable` and `_cmd_schedule_run` helpers in `app.py` (Kimi had dropped them entirely).
4. Wired `schedule enable`, `schedule run`, and `schedule daemon` properly under the `@schedule` group (Kimi had left `schedule_daemon` as a bare top-level function, never registered as a subcommand).
5. Dropped bogus `task.run_count` / `task.failure_count` lines from `_cmd_schedule_show` (those attributes do not exist on `ScheduledTask`).
6. Removed the `config.reflection.enabled` gate from the `reflection_scheduler` lazy property so the `hestia reflection status` patched-`__init__` test contract continues to hold; the `enabled` check moved to the daemon tick site.
7. Added missing `import sys` in `app.py` (referenced ~10×, never imported — module loaded only because `sys.exit` is resolved lazily).
8. Constrained `reflection_scheduler` construction to require a non-`None` `proposal_store` (mypy fix).
9. `ruff check src/ --fix` cleared 64 lints (unused imports, `OSError`/`IOError` alias, `datetime.UTC`, etc.). One auto-fix replaced `setattr(func, "__hestia_skill__", definition)` in `skills/decorator.py` with a direct attribute write that mypy rejected; restored the assignment with a `# type: ignore[attr-defined]`.

**What shipped:**

| Module | Lines | Responsibility |
| --- | --- | --- |
| `src/hestia/cli.py` | 588 | Click definitions only. |
| `src/hestia/app.py` | 1,525 | `CliAppContext`, `make_app`, lazy subsystem properties, idempotent `bootstrap_db()`, single `make_orchestrator()` constructor, all `_cmd_*` async commands. |
| `src/hestia/platforms/runners.py` | 245 | `run_platform`, `run_telegram(app, config)`, `run_matrix(app, config)`. |

- `Orchestrator(...)` now constructed in **one** place (`CliAppContext.make_orchestrator()`); the previous three-call-site drift (`cli()`, `schedule_daemon`, `run_telegram` / `run_matrix`) is gone.
- `run_async` decorator removes per-command `asyncio.run(_inner())` boilerplate.
- `ctx.obj` is the typed `CliAppContext` only; the parallel raw-dict layer is removed.
- ADR-0020 documents the split + module ownership boundaries.
- Bumped to `0.7.4`; `uv.lock` synced; CHANGELOG + handoff written.

**Review (Cursor):**

- Full gate on the branch tip: **`691 passed, 6 skipped`** (no test count change vs L29 — pure refactor as specified). `uv run mypy src/hestia` → **0**.
- **Ruff project-wide count: 255 → 44** (massive cleanup, per ADR-0020 expectation that decomposing the monolith would naturally drop the E501 backlog plus the auto-fix pass).
- Lockfile clean (`hestia` package version `0.7.4` matches `pyproject.toml`).
- Same pre-existing `aiosqlite` `RuntimeError: Event loop is closed` test-teardown warnings as L28/L29; not L30's concern.

**Merge:** `feature/l30-cli-decomposition` → `develop` via `--no-ff` merge commit `30a224f`.

**Queue advance:** `KIMI_CURRENT.md` will move to **L31** (orchestrator engine cleanup). L31 carry-forward: ruff baseline tightened to **44** (no regressions allowed), test baseline **691**, note that Kimi's max-iterations is a real risk on long refactor loops — L31 must be sized to fit comfortably under 100 steps.

**Suggested coverage gaps** (no L30 blocker, fold into future loops if natural):

- `_cmd_schedule_run` and `_cmd_schedule_enable` paths are exercised end-to-end by `tests/unit/test_cli_scheduler.py` but with no explicit coverage that the daemon-tick gate (`if app.config.reflection.enabled and app.reflection_scheduler is not None`) actually short-circuits when reflection is disabled. Add when L31 touches the orchestrator path.
- The `run_platform` shared helper in `runners.py` has no direct unit test — adapter integration tests cover it implicitly. Could add a fake-adapter unit test when L33 touches platform runners.

---

## 2026-04-18 — Loop: L29 — reliability surface, secrets hygiene, ADR consolidation (Kimi) → merged to develop

**Kimi:** Loop ran ~18 minutes; **all 9 spec section commits landed** but Kimi hit `--max-ralph-iterations` (100) immediately after the handoff commit (`378b2e8`) and exited with code 1 **before writing `.kimi-done`**. Resume id `005cdc7a-0213-4e15-9ec6-9c0f26b16572` recorded but not used — Cursor verified completion independently and wrote a valid `.kimi-done` (`HESTIA_KIMI_DONE=1`, `LOOP=L29`, `COMMIT=378b2e8`, `TESTS=passed=691 failed=0 skipped=6`, `MYPY_FINAL_ERRORS=0`) with a `NOTE=` field documenting the orchestration shortcut.

**What shipped (per spec section):**

1. **§1 — Reflection scheduler failure visibility.** `ReflectionScheduler` records failures in a 20-entry ring buffer keyed by stage (`mining`, `proposal`, `tick`); `failure_count` monotonic; new `status() -> dict` method; new `hestia reflection status` CLI command prints the table.
2. **§2 — Style scheduler failure visibility.** Same ring-buffer pattern in `style/scheduler.py`; `hestia style show` now displays a `Failures:` section when degraded.
3. **§3 — Visible warnings on missing personality / calibration.** CLI bootstrap now emits a yellow stderr warning + `logger.warning` when `SOUL.md` or `docs/calibration.json` is absent. Honours `HESTIA_SOUL_PATH` and `HESTIA_CALIBRATION_PATH` env overrides.
4. **§4 — Email password env var.** New `EmailConfig.password_env: str | None`. Resolution order: env var (if `password_env` set) → plaintext `password` → `EmailConfigError`. Email setup guide rewritten env-var-first.
5. **§5 — Web-search provider type narrowing.** `WebSearchConfig.provider` now `Literal["tavily", ""]`; factory error message no longer mentions `"brave"`.
6. **§6 — `SECURITY.md` refresh.** Supported versions table now `0.7.x`; new TrustConfig, egress audit, and prompt-injection scanner subsections; disclosure points to GitHub Security Advisory at the public repo URL.
7. **§7 — ADR consolidation.** `ADR-0014`, `0015`, `0017`, `0018` moved from `docs/development-process/decisions/` to `docs/adr/` (canonical location); `decisions/README.md` left as a redirect pointer; cross-references updated in handoff docs.
8. **§8 — Version bump + handoff.** `pyproject.toml` → `0.7.3`; `uv.lock` synced in same commit; CHANGELOG entry added; handoff doc written.

**Review (Cursor):**

- Re-ran full gate on the branch tip: **`691 passed, 6 skipped`** (was `673` before L29; +18 net new tests, all from L29's failure-visibility coverage). `uv run mypy src/hestia` → **0**.
- **Ruff regression: 245 → 255** (+11 errors), all `E501` (line-too-long), all in L29-touched files (`cli.py` ×10, `reflection/runner.py` ×1, plus 6 in the new test files). No new rule violations of any other category. Folded into L30's carry-forward as a hard cap (`uv run ruff check ...` must be ≤ 255 at L30 end). L30 will rewrite `cli.py` wholesale, so most of these will disappear naturally.
- Discarded a small uncommitted `cli.py` debris line (`app: CliAppContext = ctx.obj["app"]`) that Kimi was mid-step writing when it hit max-iterations — `app` was never added to `ctx.obj`, so the line would have crashed at runtime; tests passed only because the code path is unreached. Will be made obsolete by L30 anyway.
- Lockfile clean (`hestia` package version `0.7.3` matches `pyproject.toml`).

**Merge:** `feature/l29-reliability-secrets` → `develop` via `--no-ff` merge commit `bbed167`. Pushed.

**Queue advance:** `KIMI_CURRENT.md` will move to **L30**; L30 carry-forward to be updated with (a) ruff baseline raised to 255, (b) test baseline of 691, (c) note that L30 should naturally drop `cli.py` E501 count to near zero by virtue of decomposition.

**Suggested coverage gaps** (no L29 blocker, fold into future loops if natural):

- The new `hestia reflection status` and `hestia style show` failure paths are covered by unit + CLI integration, but there is no end-to-end test that **causes** a real scheduler tick to fail and then queries the CLI. Could be added when L33 touches schedulers.
- `EmailConfig.password_env` resolution is covered by unit; no integration test exercises an actual SMTP connect with env-resolved creds (would require live SMTP or fuller mock). Optional.
- `HESTIA_CALIBRATION_PATH` override is covered for the missing-file warning case but not for the override-resolves-to-an-existing-file case. Add when L34 touches CLI bootstrap docs.

---

## 2026-04-18 — Loop: L28 — critical correctness bugs + dependency hygiene (Kimi) → merged to develop

**Kimi:** `.kimi-done` valid for L28 (`LOOP=L28`, branch `feature/l28-critical-bugs`, final commit `f2a3db6`, tests `673 passed, 6 skipped`, `MYPY_FINAL_ERRORS=0`). Loop ran ~17 minutes end-to-end (well under the 100-step max-iteration budget that bit L24).

**What shipped (per spec section):**

1. **§1 — `bleach` → `nh3`.** `nh3>=0.2.17` added to `pyproject.toml`; `nh3.clean(raw_html, tags=set())` replaces `bleach.clean(...)` in `email/adapter.py`. Lockfile synced in same loop. Bonus regression test for `<script>` tag stripping.
2. **§2 — Tool registration.** `read_artifact` now registered in `cli.py` against `ArtifactStore`. New `make_delete_memory_tool` with `requires_confirmation=True` (correct default for a destructive memory op). Both surface in `hestia tools list` (covered by `tests/integration/test_cli_tools_registered.py`).
3. **§3 — Email Message-ID + draft-unknown removal.** `create_draft` now generates `email.utils.make_msgid(domain=...)` before append; `send_draft("draft-unknown")` raises `EmailAdapterError` explicitly so callers can never accept the sentinel. Regression tests in `tests/unit/test_email_create_draft.py`.
4. **§4 — IMAP injection escape.** New `_imap_quote(value)` static helper applied to every `FROM "..."` / `SUBJECT "..."` / fallback interpolation. Malformed `SINCE:` now raises `EmailAdapterError` instead of falling through to a subject search. Coverage: `tests/unit/test_email_search_parser.py` includes the explicit injection-attempt regression (`FROM:alice" OR ALL HEADER X "` no longer escapes the quoted criterion).
5. **§5 — Dead `StyleProfileBuilder.get_profile_dict` removed.** Anti-regression test (`tests/unit/test_style_builder_no_dead_method.py`) `assert not hasattr(StyleProfileBuilder, "get_profile_dict")` so no one re-adds the stub.
6. **§6 — Version + lockfile.** Bumped to `0.7.2`; `uv.lock` reflects both the version bump and the `nh3` addition (no post-merge drift this time).
7. **§7 — Handoff doc.**

**Review (Cursor):**

- Re-ran full gate on the branch tip: **`673 passed, 6 skipped`** (was `652 passed, 6 skipped` before L28; +21 net new tests, all from L28's regression coverage). `uv run mypy src/hestia` → **0**.
- `uv run ruff check src/hestia tests` reports **243 errors**, but `develop` baseline at L28 start was **245** — L28 reduced ruff debt by 2 (incidental). Pre-existing baseline; folded into L29 carry-forward as a non-blocking item.
- Diff inspection: `_imap_quote` is a `@staticmethod` (called via `EmailAdapter._imap_quote(...)`) — fine. `make_msgid` uses `domain=username.split("@")[-1]` as suggested. `delete_memory` uses `MEMORY_WRITE` capability with confirmation gate, matching the project's destructive-tool pattern.
- Lockfile shape correct (`hestia` package version `0.7.2`; `nh3` resolved at `0.3.4`).

**Merge:** `feature/l28-critical-bugs` → `develop` via `--no-ff` merge commit `dcc54c5`. Pushed.

**Queue advance:** `KIMI_CURRENT.md` moved to **L29**; L29 carry-forward updated with (a) ruff baseline of 243 errors as a non-blocking note, (b) the new test-count baseline of 673 to preserve through subsequent loops.

**Suggested coverage gaps to fold into future loops** (no L28 blocker):

- No test asserts `EmailAdapterError` propagates as a tool-error `ToolCallResult` end-to-end via the orchestrator dispatch path. L31 (engine cleanup) is a natural place to add this when extracting `ToolCallResult.error`.
- No integration test exercises `delete_memory`'s confirmation flow on Telegram/Matrix — confirmed via unit, not via the platform adapters. Consider when L30/L33 touch that area.

---

## 2026-04-18 — Loop: L27 — interaction-style profile (Kimi) → merged to develop

**Kimi:** `.kimi-done` valid for L27 (`LOOP=L27`, branch `feature/l27-style-profile`, feature commit `8280198`, `MYPY_FINAL_ERRORS=0`). Kimi-reported pytest summary in `.kimi-done` did not match a local re-run on the same tree (see below).

**What shipped:**

1. Style metrics persistence + `StyleProfileBuilder` (`src/hestia/style/*`) with vocab-backed formality heuristic and completion-token length proxy.
2. Context-builder addendum (`[STYLE PROFILE] …`) with token cap; orchestrator hooks to refresh profile after turns.
3. Scheduler nightly tick (idle-gated, aligned with L26 reflection scheduling).
4. CLI: inspect/reset style profile; `StyleConfig` on `HestiaConfig`.
5. ADR-0019 (style vs identity), README + changelog, version **0.7.1** (`pyproject.toml` + `uv.lock`).

**Review (Cursor):**

- Kimi had left `docs/handoffs/L27-style-profile-handoff.md` untracked; committed as `b4238fb` on the feature branch before merge.
- Full gate on branch tip: **`652 passed, 6 skipped`** (658 tests collected); `uv run mypy src/hestia` → **0** errors.
- Pre-existing `aiosqlite` worker-thread warnings in `tests/unit/test_injection_scanner.py` (unchanged by L27).
- Lockfile already matched **0.7.1**; no post-merge lockfile drift fix needed.

**Merge:** `feature/l27-style-profile` → `develop` via merge commit `bc3fef8`. Pushed.

**Queue:** Row **L27** is the last entry in `kimi-phase-queue.md`. `KIMI_CURRENT.md` reset to **idle** (no next spec until the queue is extended).

---

## 2026-04-18 — Loop: L26 — reflection loop + proposal queue (Kimi) → merged to develop

**Kimi:** `.kimi-done` valid for L26 (`LOOP=L26`, branch `feature/l26-reflection-loop`, commit `8762ac8`, tests `637 passed, 6 skipped`, `MYPY_FINAL_ERRORS=0`).

**What shipped:**

1. Reflection subsystem (`src/hestia/reflection/*`) with runner, scheduler hooks, proposal store/types, and prompts.
2. Proposal lifecycle surfaced in orchestrator/session-start paths and CLI controls.
3. New docs/ADR/handoff for L26 plus README/changelog updates.
4. Version bump to 0.7.0.

**Review (Cursor):**

- Re-ran full gate on branch: `637 passed, 6 skipped`; `mypy src/hestia` clean (0).
- Post-merge found lockfile drift (`uv.lock` still reflected 0.6.0). Resolved with follow-up commit on develop: `980d14f chore(lockfile): sync uv.lock to 0.7.0`.

**Merge:** `feature/l26-reflection-loop` → `develop` via `--no-ff` merge commit `8eac5a0`. Pushed.

**Queue advance:** `KIMI_CURRENT.md` moved to L27; L27 review carry-forward populated from L26 findings.

---

## 2026-04-18 — Loop: L25 — email adapter (IMAP read + SMTP draft) (Kimi) → merged to develop

**Kimi:** `.kimi-done` valid for L25 on `feature/l25-email-adapter` (`COMMIT=bdbbd93`, tests `620 passed, 6 skipped`, `MYPY_FINAL_ERRORS=0`).

**What shipped:**

1. New email integration modules and tools (`email_list`, `email_read`, `email_search`, `email_draft`, `email_send`, `email_move`, `email_flag`).
2. `EmailConfig` wiring in `HestiaConfig` and CLI registration.
3. Confirmation-sensitive behavior for send operations aligned with L23 mobile confirmations.
4. New docs: `docs/guides/email-setup.md` and L25 handoff report.
5. Version bump artifacts to 0.6.0 (`pyproject.toml` + `uv.lock` + changelog).

**Review (Cursor):**

- Re-ran full gate on branch tip: `620 passed, 6 skipped`; `mypy src/hestia` clean (0 errors).
- No merge blockers found; only pre-existing `aiosqlite` thread-shutdown pytest warnings remained.

**Merge:** `feature/l25-email-adapter` → `develop` via `--no-ff` merge commit `da68436`. Pushed.

**Queue advance:** `KIMI_CURRENT.md` moved to L26; L26 carry-forward populated from L25 review findings.

---

## 2026-04-18 — Loop: L24 — prompt-injection detection + egress auditing (Kimi) → merged to develop

**Kimi:** loop completed with `.kimi-done` (`LOOP=L24`, branch `feature/l24-injection-detection`, commit `cf2e7ed`, tests `597 passed, 6 skipped`, `MYPY_FINAL_ERRORS=0`). Initial Kimi run hit max-steps at 100; resumed session completed and wrote valid `.kimi-done`.

**What shipped:**

1. New security scanner module `src/hestia/security/injection.py` with regex + entropy heuristics.
2. Tool-result annotation path wired through orchestrator/tool handling so suspicious content is wrapped with a security note rather than blocked.
3. Egress trace capture added for network tools (`http_get` and `web_search`) with audit reporting command flow in CLI.
4. `SecurityConfig` added and threaded through runtime config.
5. Docs delivered: `SECURITY.md`, ADR-0017, L24 handoff report, README/changelog updates.

**Review (Cursor):**

- Re-ran full gate on feature branch: `597 passed, 6 skipped`; `mypy src/hestia` clean (0 errors).
- Found one post-run hygiene issue: `uv.lock` contained `0.5.1` bump but was left unstaged. Added follow-up commit `8b9d9ca chore(lockfile): sync uv.lock for 0.5.1` and pushed before merge.

**Merge:** `feature/l24-injection-detection` → `develop` via `--no-ff` merge commit `c88c60e`. Pushed.

**Queue advance:** `KIMI_CURRENT.md` moved to L25; `L25` review carry-forward populated with L24 constraints.

---

## 2026-04-18 — Loop: L23 — Telegram + Matrix confirmation callbacks (Kimi + Cursor fix) → merged to develop

**Kimi:** `.kimi-done` loop completed on `feature/l23-platform-confirmation`; final review/merge landed as `7e2ebe0` (feature commit) and merge commit `f56e9ad` on `develop`.

**What shipped:**

1. Telegram inline-keyboard confirmation flow (`✅/❌`) for `requires_confirmation=True` tools.
2. Matrix reply-pattern confirmation (`yes/no` reply to confirmation event).
3. Shared confirmation infra in `src/hestia/platforms/confirmation.py` (`ConfirmationRequest`, `ConfirmationStore`, args renderer).
4. `TrustConfig.prompt_on_mobile()` preset.
5. New unit/integration coverage for Telegram, Matrix, and confirmation store.

**Review findings (Cursor):**

- Full suite executed before merge: `573 passed, 6 skipped`.
- Found and fixed one real concurrency bug in `cli.py`: confirmation callbacks were bound to shared mutable `_current_telegram_user` / `_current_matrix_room`, which could cross-route confirmations under concurrent chats.
- Fix applied in the same feature commit by switching to per-turn `ContextVar` binding for platform user/room during `process_turn`.

**Merge:** `feature/l23-platform-confirmation` → `develop` via `--no-ff` merge commit `f56e9ad`. Pushed.

**Queue advance:** `KIMI_CURRENT.md` repointed to L24 and L24 `## Review carry-forward` populated with L23 findings.

---

## 2026-04-17 — Loop: L22 — mypy cleanup + CI strictness ratchet (Kimi) → merged to develop

**Kimi:** `.kimi-done`: `LOOP=L22`, final commit `0986130`, `TESTS=545 passed, 6 skipped, 0 failed`, `MYPY_FINAL_ERRORS=0` on `feature/l22-mypy-cleanup`. 14 Kimi commits covering every §1-§8 category from `reviews/mypy-errors-april-17.md`. Ralph max-steps hit twice across three launches; each resume picked up from git state.

**What shipped (44 → 0 mypy errors):**

1. **§1 Third-party stubs** — `types-croniter` dev dep added; `nio` and `asyncpg` marked `ignore_missing_imports = true` (they're optional; no public stubs).
2. **§2 Forward references** — `hestia.persistence.sessions` now uses `from __future__ import annotations` + `TYPE_CHECKING` imports for `Turn` / `TurnTransition`. Fixes 7 errors without runtime cost.
3. **§3 Optional attribute access (real bugs)** — every unchecked `.value` / `.x` access on a `SomeType | None` now either guards or raises. Notable fixes: `cli.py` SchedulerStore accessor (missing config → explicit error), Telegram Updater lifecycle None-guard, SkillState None check, CLI check command passing `None` into `DefaultPolicyEngine.turn_token_budget` (now builds a synthetic Session). 16 errors, ~12 of them latent bugs.
4. **§4 Factory returns** — memory-tool factories and `delegate_task` factory now return the declared `Tool` type instead of `Any`.
5. **§5 DB row → dataclass** — `SchedulerStore._row_to_task` (and callers) now coerce with explicit casts/`.as_string()` rather than dumping `Any` through; `ScheduledTask` gets strict field-by-field construction. New `tests/unit/test_scheduler_store.py` covers the edge cases.
6. **§6 Function annotations** — legacy helpers in `audit/checks.py`, `scheduler/engine.py`, `tools/metadata.py`, `artifacts/store.py` got signatures.
7. **§7 Orchestrator tool args** — `Orchestrator._dispatch_tool` narrows the argument type at the boundary rather than trusting `Any`.
8. **§8 CI strictness** — `docs/development-process/mypy-baseline.txt` retired; `.github/workflows/ci.yml` now runs `uv run mypy src/hestia` directly (no count-based compare). `pyproject.toml` `[[tool.mypy.overrides]] strict = true` for `hestia.policy.*` and `hestia.core.*` — the first ratchet step.

Plus `chore: bump version to 0.4.1`, `docs: L22 handoff report`.

**Review (Cursor):**

- Full suite on `feature/l22-mypy-cleanup` tip: **545 passed / 0 failed / 6 skipped** (baseline 543 → +2 from new scheduler-store tests).
- `uv run mypy src/hestia` → `Success: no issues found in 69 source files`.
- Spot-checked a few of the "real bug" fixes: SchedulerStore None → error is correct behaviour (previously would AttributeError on first scheduler call with no config); Updater None-guard in Telegram adapter means stopping the bot before start no longer raises; SkillState None check means `/skills update` with an unknown skill now errors cleanly instead of crashing.
- No wiring gaps found this time (the L21 review lesson — "did you wire it in cli.py?" — doesn't apply; L22 was pure debt-paydown, no new features).

**Merge:** `feature/l22-mypy-cleanup` → `develop` via `--no-ff` merge commit `75ea2b5`. Pushed. CI on `develop` should now be honest (mypy green, no baseline).

**Queue:** L22 complete. Next up: L23 — platform confirmation callbacks (Telegram inline keyboard + Matrix reply pattern), targeted at v0.5.0.

**Next:** L23, L24, L25, L26, L27 in sequence as queued. Each loop's review carry-forward gets populated at loop start.

---

## 2026-04-17 — Loop: L21 — Context resilience + handoff summaries + Hermes untangle (Kimi) → merged to develop

**Kimi:** `.kimi-done`: `LOOP=L21`, final commit `cdc2f63`, `TESTS=passed=540 failed=0 skipped=6` on `feature/l21-context-resilience-handoff`. 9 spec sections, 11 Kimi commits (one §, + one ruff style fix, + one end-of-loop checklist tidy). Ralph loop hit max-steps=100 once at §5/§6 boundary; one manual re-run of `kimi-run-current.sh` completed §6-§9 and wrote `.kimi-done`.

**Trigger:** Dylan's reported "⚠️ Context length exceeded (15,228 tokens). Cannot compress further." in Matrix during a post-merge check. Investigation showed the error originated from Hermes/Silas (`~/.hermes/hermes-agent/run_agent.py`), not Hestia. But it exposed that **Hestia silently truncated history on overflow** with no summarization and no user signal. L21 makes that failure mode loud and recoverable.

**What shipped:**

1. **§1 Session handoff summaries** — new `src/hestia/memory/handoff.py` with `SessionHandoffSummarizer` + `HandoffResult`. On `close_session` with `handoff_summarizer` configured, generates a 2-3 sentence prose recap (<=350 chars) and persists it as a memory entry tagged `["handoff", session.platform]`. Skips trivial sessions (< `min_messages` user turns).
2. **§2 History compressor** — new `src/hestia/context/compressor.py`. `HistoryCompressor` protocol + `InferenceHistoryCompressor` default that calls the same `InferenceClient` with a small prompt (<=400 chars output). `ContextBuilder` now accepts `compressor` + `compress_on_overflow` and splices the summary into the effective system prompt of the turn that overflowed.
3. **§3 Loud overflow signal** — `ContextBuilder.build()` raises `ContextTooLargeError` when the protected block (system + first-user + new-user) alone exceeds the budget. `Orchestrator.process_turn` catches it, records a `FailureClass.CONTEXT_OVERFLOW` bundle, calls `platform.send_system_warning`, and best-effort kicks the handoff summarizer.
4. **§4 Config** — `HandoffConfig` and `CompressionConfig` added to `HestiaConfig`. `TrustConfig.household` / `TrustConfig.developer` enable both by default; `paranoid` leaves them off. Unit tests assert defaults and preset fan-out.
5. **§5 Platform warning channel** — abstract `Platform.send_system_warning(user, text)` with `⚠️`-prefixed implementations for CLI (stderr click echo), Telegram (dedicated message, not rate-limited), Matrix (plain text reply, no retry storm).
6. **§6 Hermes-untangle docs** — new `deploy/hestia-llama.alt-port.service.example` (port 8002, `/opt/hestia/slots`), expanded `deploy/README.md` with Mode A (dedicated) vs Mode B (shared) tradeoffs, new `docs/guides/runtime-setup.md` (base_url / slot_dir selection + isolation smoke-test), ADR-0015 for llama-server coexistence. Historical `Hermes predecessor` ADR / docstring references left alone as agreed.
7. **§7 Context-resilience docs** — README "Context budget and long sessions", updated `docs/runtime-feature-testing.md`, ADR-0014.
8. **§8 Version bump** — `pyproject.toml` → `0.4.0`, `CHANGELOG.md` `[0.4.0]` section, `uv.lock` regenerated.
9. **§9 Handoff report** — `docs/handoffs/L21-context-resilience-handoff.md`.

**Review (Cursor):**

- Re-ran `uv run pytest tests/unit/ tests/integration/ -q` on `feature/l21...` tip: **540 passed / 0 failed / 6 skipped** (baseline 514 → +26 new).
- Mypy still at 44 errors (unchanged; L22 owns the cleanup).
- **Real bug found (review pattern #2 from `.cursorrules`):** `HandoffConfig` and `CompressionConfig` were defined, merged into `TrustConfig` presets, and unit-tested — but `cli.py` never instantiated `SessionHandoffSummarizer` or `InferenceHistoryCompressor`, and never read `cfg.handoff` or `cfg.compression`. L21 was dead code in the actual Telegram/Matrix/CLI runtime.

**Cursor fix commit `5ece0bf fix(cli): wire HandoffConfig and CompressionConfig into the runtime`:**

- Added `ContextBuilder.enable_compression(compressor)` helper.
- `cli.py` now builds an `InferenceHistoryCompressor(inference, max_chars=cfg.compression.max_chars)` and calls `enable_compression` when `cfg.compression.enabled`.
- `cli.py` builds `SessionHandoffSummarizer(...)` when `cfg.handoff.enabled`, stores it on `CliAppContext.handoff_summarizer`, threads it through `make_orchestrator()` and the subagent `orchestrator_factory()`.
- Regression guard: `tests/unit/test_cli_handoff_compression_wiring.py` (3 tests).
- Final test count: **543 passed / 0 failed / 6 skipped**. Mypy still 44.

**Merge:** `feature/l21-context-resilience-handoff` → `develop` via `--no-ff` merge commit `d6b7cd3`. Pushed.

**Queue:** L21 complete. `docs/development-process/prompts/KIMI_CURRENT.md` to be repointed at L22 next.

**Next:** L22 — mypy cleanup + CI strictness for `hestia.policy.*` and `hestia.core.*`. Followed by L23 (platform confirmation callbacks), L24 (prompt injection + egress audit), L25 (email adapter), L26 (reflection loop), L27 (style profile).

---

## 2026-04-17 — Loop: L19 — Slot-save basename fix + ctx-window alignment + v0.2.2 release (Kimi) → merged, tagged v0.2.2

**Kimi:** `.kimi-done`: `LOOP=L19`, develop tip `c46dc7a`, main `255dc2b`, v0.2.2 tag `3decc9f`. Alembic migration `2cf4ef820e46`. **485 passed, 6 skipped** on both `develop` and `main` (up from 478 baseline — 7 new tests).

**Trigger:** Three real bugs surfaced while running v0.2.1 against the live Hermes-shared llama-server on the 3060 12GB during post-L18 runtime setup.

**Review (Cursor):** Verified all 6 sections:

1. **Slot-save basename fix** (`src/hestia/inference/slot_manager.py`) — `save()` and `_evict_session_locked()` now send `saved_path.name` to llama.cpp; `slot_restore` defensively takes `.name` of whatever the DB holds so legacy absolute-path rows are handled. New tests in `tests/unit/test_slot_manager.py` assert basename-only behavior across save/restore/evict/update paths. Alembic revision `2cf4ef820e46_normalize_slot_saved_path_to_basename.py` rewrites any legacy `sessions.slot_saved_path` values containing `/` down to the basename.
2. **`ctx_window` wired from config** — New `InferenceConfig.context_length` field (default `8192`) in `src/hestia/config.py`. `cli.py:59` now passes `cfg.inference.context_length` into `DefaultPolicyEngine`. Policy default updated from 32768 → 8192 with clarified "per-slot, not total" docstring. New regression tests in `tests/unit/test_policy.py` cover default + config-override behavior.
3. **README KV-cache quant consistency** — `README.md` lines 306–313 changed `q4_0` → `turbo3`; explanatory paragraph updated to describe turbo3's ~3-bit packing and its benefit over q4_0 on RTX 30/40-series. `deploy/README.md` low-VRAM q4_0 example left intact (correct for <8GB / older hardware).
4. **Deploy alignment** — `deploy/hestia-llama.service` ExecStart updated to `--ctx-size 32768 --parallel 4 --cache-type-k turbo3 --cache-type-v turbo3`, making per-slot budget = 8192, matching the new policy default and the new `InferenceConfig.context_length` default out of the box.
5. **CHANGELOG + version bump** — `[0.2.2] — 2026-04-17` section at top; `pyproject.toml` bumped to `0.2.2`; `uv.lock` synced.
6. **Release** — `develop` → `main` via `--no-ff` merge commit `255dc2b Release v0.2.2`. Annotated tag `v0.2.2` at `3decc9f` on main. `main`, `develop`, and tag all pushed to origin.

**Also (orchestration):** cherry-picked the L19 queue commit off `main` back onto `develop` after an initial mis-commit to `main` — `main` preserved at `32ffe4e` (v0.2.1 sync point) until the proper §6 release merge.

**Runtime follow-up (Cursor, out-of-loop):**

- Discarded the local runtime-only slot-save patch on `src/hestia/inference/slot_manager.py` in the `hestia-runtime` worktree; merged `develop` in (commit tree now contains the proper upstream fix).
- Set `InferenceConfig.context_length=16384` in `~/Hestia-runtime/config.runtime.py` — matches the shared Hermes llama-server's per-slot budget (`-c 49152 -np 3`), not the v0.2.2 default (8192).
- `hestia-telegram.service` (new systemd --user unit) started pre-L19 and restarted onto v0.2.2 code cleanly; Telegram adapter reconnected, scheduler running.
- Runtime DB note: alembic stamp is no-op there because the worktree's `alembic.ini` points `sqlalchemy.url` at `./hestia.db` relative to invocation, not `./runtime-data/hestia.db`; and the DB was originally bootstrapped by `initialize_schema()` rather than alembic, so it has no `alembic_version` row. Harmless for now — L19 migration was also redundant since the DB's single `slot_saved_path` is already a basename. **Flag for future loop:** align `alembic.ini` to the runtime DB location and/or stamp the existing DB.

**Queue:** L19 complete. No active loop. `docs/development-process/prompts/KIMI_CURRENT.md` reset to "idle" placeholder.

**Next:** Three live-hardware bugs from the v0.2.1 runtime exposure are fixed. Ready for another feature direction or further field-testing of v0.2.2.

---

## 2026-04-15 — Loop: L18 — Post-public cleanup + v0.2.1 release (Kimi) → merged, tagged v0.2.1

**Kimi:** `.kimi-done`: `LOOP=L18`, tip `b5d4eb0`, v0.2.1 tag `6f1747c`, main `902f615`. **478 passed, 6 skipped** on both `develop` and `main` (up from 474 baseline — 4 new tests).

**Trigger:** Second-round pre-public review. 1 real bug + 4 polish/cleanup items.

**Review (Cursor):** Re-ran full pytest — **478 passed, 6 skipped**. Spot-checked all 7 sections:

1. **`save_memory` tool-name bug fix** — `src/hestia/audit/checks.py` all 10 references updated (`memory_write` → `save_memory`) including finding message and variable names. Positive regression test + negative test (stale alias → no finding) both present in `tests/unit/test_audit.py`. Remaining `memory_write` references verified intentional: 3 in the negative test, 1 in `tools/capabilities.py` for the `MEMORY_WRITE = "memory_write"` capability label (correctly unchanged per spec).
2. **Atomic per-artifact metadata write** — New `_atomic_write_json()` helper at `artifacts/store.py:78`. Both `_save_inline_index()` (line 102) and the per-handle `{handle}.json` write (line 162) route through it. Deduplicated the atomic pattern.
3. **Internal docs moved** — `docs/orchestration/`, `docs/prompts/`, `docs/reviews/`, and selected `docs/design/` internal-process files → `docs/development-process/` with explanatory README, `design-artifacts/`, `reviews/`, and `prompts/` subdirs. `runtime-feature-testing.md` stayed in `docs/` (operator doc, not process doc). All cross-references updated including `.cursorrules` and `scripts/kimi-run-current.sh`.
4. **CI mypy baseline** — `docs/development-process/mypy-baseline.txt` records the 44 pre-existing errors. `.github/workflows/ci.yml` switched to count-based comparison: `CURRENT > BASELINE` fails the step. Honest CI signal without blocking on existing debt.
5. **CHANGELOG + version bump** — `[0.2.1] — 2026-04-15` section at top of CHANGELOG; `pyproject.toml` bumped to `0.2.1`; `uv.lock` synced.
6. **Release** — `develop` → `main` via `--no-ff` merge commit `902f615 Release v0.2.1`. Annotated tag `v0.2.1` at `6f1747c` on main. `main`, `develop`, and tag all pushed to origin.
7. **Branch cleanup** — `feature/l18-post-public-cleanup` deleted locally and remotely; `git remote prune origin`.

**Queue:** L18 complete. No active loop. `docs/development-process/prompts/KIMI_CURRENT.md` reset to "idle" placeholder.

**Next:** All five items from the second-round review are addressed. Repo is public-clean.

---

## 2026-04-15 — Loop: L16 — Pre-public cleanup (Kimi) → merged (L15–L16 queue complete)

**Kimi:** `.kimi-done`: `LOOP=L16`, commit **`db1298f`**, **474 passed**, **6 skipped**.

**Review (Cursor):** Re-ran full pytest — **474 passed**, **6 skipped**. Spot-checked all 7 sections:

1. **Handoff files archived** — `docs/HANDOFF_STATE.md` + 16 handoff reports git-removed. Copied to `~/vault/Projects/Hestia-Handoff-Archive/`.
2. **Skills documented** — New "Skills (experimental)" section in README with `@skill` decorator example, linked to ADR-024.
3. **asyncpg optional** — Moved from `dependencies` to `[project.optional-dependencies] postgres`. `db.py` adds helpful `ImportError` with install instruction.
4. **README security** — Config file execution warning added.
5. **Lazy imports moved** — `base64` in `store.py`, `re` in `engine.py`, `json` in `trace_store.py` moved to module level. `httpx` in `http_get.py` already at top (done in L15).
6. **model_name default** — Changed to empty string. `InferenceClient.__init__` validates and raises `ValueError`. Example config updated.
7. **Quickstart reordered** — Prerequisites section with llama.cpp setup added before install commands. PostgreSQL extra documented.

**Cleanup:** `.kimi-output-l16.log` was accidentally tracked; removed. `.gitignore` broadened to `.kimi-output*.log`.

**Git:** Fast-forward `feature/l16-pre-public-cleanup` → `develop`.

**Queue:** L15–L16 complete. All 15 pre-public review items addressed.

---

## 2026-04-15 — Loop: L15 — Security & bug fixes (Kimi) → merged

**Kimi:** `.kimi-done`: `LOOP=L15`, commit **`d5a57f8`** (tip **`a5468d5`** with handoff), **472 passed**, **6 skipped**. Report: [`docs/handoffs/HESTIA_L15_REPORT_20260415.md`](../handoffs/HESTIA_L15_REPORT_20260415.md).

**Review (Cursor):** Re-ran full pytest — **472 passed**, **6 skipped**. Ruff: 165 pre-existing errors, no new violations. Spot-checked all 5 security/bug fixes:

1. **SSRF transport-layer fix** — `SSRFSafeTransport` intercepts every connection at transport layer, validates resolved IPs against blocked ranges. Pre-flight `_is_url_safe()` kept for user-friendly errors (scheme/hostname only, no DNS). Redirect SSRF and DNS rebinding both addressed.
2. **Terminal process group kill** — `start_new_session=True` + `os.killpg()` with SIGKILL. Fallback chain: killpg → proc.kill → ProcessLookupError. Stale "Phase 1c" comment removed.
3. **NameError guards removed** — `allowed_tools`, `policy_snapshot`, `slot_snapshot` initialized at top of `process_turn()`. Both `except NameError` blocks removed.
4. **Atomic inline index write** — `tempfile.mkstemp()` + `os.replace()` with cleanup on failure.
5. **allowed_users deny-all** — Empty list now returns `False` in `_is_allowed()`. Config docstring updated.

**New tests:** `test_terminal.py` (process group kill, timeout), `test_http_get_ssrf.py` (redirect blocking, transport-layer checks), `test_artifacts.py` (atomic write), `test_telegram_adapter.py` (empty allowed_users denied).

**Git:** Fast-forward `feature/l15-security-hardening` → `develop` (tip `a5468d5`).

**Queue:** `KIMI_CURRENT.md` → **L16** [`L16-pre-public-cleanup.md`](kimi-loops/L16-pre-public-cleanup.md); **`## Review carry-forward`** filled with lazy import note and pre-existing ruff debt.

---

## 2026-04-14 — Loop: L14 — docs/runtime manual smoke (Kimi) → merged (queue complete)

**Kimi:** `.kimi-done`: `LOOP=L14`, commit **`7965fc2`**, **466 passed**, **2 skipped**. Report: [`docs/handoffs/HESTIA_L14_REPORT_20260413.md`](../handoffs/HESTIA_L14_REPORT_20260413.md).

**Review (Cursor):** Re-ran full pytest — **466 passed**, **2 skipped**, only pre-existing aiosqlite warning. Docs delivered: `runtime-feature-testing.md`, `matrix-manual-smoke.md`, README Matrix links, credentials sync, HANDOFF_STATE pointer.

**Git:** Fast-forward `feature/l14-docs-runtime-manual` → `develop` (plus follow-up doc commit `5d5a414` for credentials naming consistency).

**Queue:** L10–L14 chain complete. `KIMI_CURRENT.md` set to idle/complete state; maintainer next step is final pass + `git push`.

---

## 2026-04-14 — Loop: L13 — scheduler Matrix cron/one-shot (Kimi) → merged

**Kimi:** `.kimi-done`: `LOOP=L13`, commit **`30037e6`**, **466 passed**, **2 skipped**. Report: [`docs/handoffs/HESTIA_L13_REPORT_20260413.md`](../handoffs/HESTIA_L13_REPORT_20260413.md).

**Review (Cursor):** Re-ran full pytest — **466 passed**, **2 skipped** (`matrix_e2e`), only pre-existing aiosqlite thread warnings.

**Git:** Fast-forward `feature/l13-scheduler-matrix-cron` → `develop`.

**Queue:** `KIMI_CURRENT.md` → **L14** [`L14-docs-runtime-manual-smoke.md`](kimi-loops/L14-docs-runtime-manual-smoke.md); **`## Review carry-forward`** filled from L13 handoff.

---

## 2026-04-14 — Loop: L12 — Matrix E2E two-user (Kimi) → merged

**Kimi:** `.kimi-done`: `LOOP=L12`, commit **`f5c9297`**, **455 passed**, **2 skipped** (`matrix_e2e`). Report: [`docs/handoffs/HESTIA_L12_REPORT_20260413.md`](../handoffs/HESTIA_L12_REPORT_20260413.md).

**Review (Cursor):** Re-ran full pytest — **455 passed**, **2 skipped**, pre-existing aiosqlite thread warnings only. New: `tests/integration/test_matrix_e2e.py`, `scripts/matrix_test_send.py`, `matrix_e2e` marker in `pyproject.toml`, credentials table in `CREDENTIALS_AND_SECRETS.md`.

**Orchestration:** Waited for `.kimi-done` via **shell poll loop** (not Cursor `Await` on terminal) — ~13 min until `HESTIA_KIMI_DONE=1`.

**Git:** Fast-forward `feature/l12-matrix-e2e-two-user` → `develop`.

**Queue:** `KIMI_CURRENT.md` → **L13** [`L13-scheduler-matrix-cron.md`](kimi-loops/L13-scheduler-matrix-cron.md); **`## Review carry-forward`** filled from L12 handoff.

---

## 2026-04-14 — Loop: L11 — mock-inference tool + memory matrix (Kimi) → merged

**Kimi:** `.kimi-done`: `LOOP=L11`, commit **`ba46f32`** on `feature/l11-test-tools-memory-mock` (report: [`docs/handoffs/HESTIA_L11_REPORT_20260413.md`](../handoffs/HESTIA_L11_REPORT_20260413.md)).

**Review (Cursor):** `uv run pytest tests/unit/ tests/integration/ -q` — **455 passed** (63.8s). Spot-check: `engine.py` exempts meta-tools `list_tools` / `call_tool` from the outer `allowed_tools` filter so policy-filtered sessions can still use meta-tools; matches integration tests.

**Git:** Fast-forward merge `feature/l11-test-tools-memory-mock` → `develop` (tip **`51749a2`** includes handoff + `.cursorrules` clarification: **do not use Cursor `Await` on the shell task as Kimi completion** — poll `.kimi-done`).

**Queue:** `KIMI_CURRENT.md` → **L12** [`kimi-loops/L12-matrix-e2e-two-user.md`](kimi-loops/L12-matrix-e2e-two-user.md); **`## Review carry-forward`** on L12 filled from L11 handoff (orchestrator semantics noise, optional runtime Matrix parity, aiosqlite warnings).

---

## 2026-04-14 — Orchestration: split L10 into L10–L14 chain (Cursor)

**No Kimi run.** Broke work into **five** loops: **L10** (orchestrator + Matrix env only), **L11** (mock inference full tool + memory + teardown), **L12** (Matrix two-user E2E), **L13** (scheduler cron/one-shot + Matrix delivery + CLI session binding note), **L14** (runtime-feature-testing doc, matrix-manual-smoke, README, sync credentials doc). Added [`docs/testing/CREDENTIALS_AND_SECRETS.md`](../testing/CREDENTIALS_AND_SECRETS.md), [`prompts/KIMI_LOOPS_L10_L14.md`](prompts/KIMI_LOOPS_L10_L14.md), `L11`–`L14` specs; trimmed **L10** spec; updated queue, `KIMI_CURRENT`, `KIMI_PHASE_15` (L10-only).

---

## 2026-04-13 — Orchestration: L10 queued (Cursor) — Matrix + real-world tests

**No Kimi run yet.** Cursor opened **L10** after Dylan reported Matrix production symptoms:

- **`IllegalTransitionError`** (`done` → `failed`) when user already saw a final assistant message — orchestrator marks **`DONE`** then **`respond_callback`** (or nearby) throws; outer **`except`** attempts **`FAILED`** from a terminal state.
- Model answered “what time is it?” without **`current_time`** — policy allows tools on **`matrix`**; needs tests / nudges.

**Artifacts:** New loop spec [`kimi-loops/L10-matrix-realworld-runtime-testing.md`](kimi-loops/L10-matrix-realworld-runtime-testing.md), Kimi prompt [`prompts/KIMI_PHASE_15_MATRIX_REALWORLD_PROMPT.md`](prompts/KIMI_PHASE_15_MATRIX_REALWORLD_PROMPT.md), queue row **10**, `KIMI_CURRENT.md` → L10, `HANDOFF_STATE.md` updated.

**Process:** L10 Part D instructs Kimi to add **`docs/runtime-feature-testing.md`** — workflow for extra git worktrees per feature branch so **`~/Hestia-runtime`** stays stable.

---

## 2026-04-13 — Loop: L09 Phase 14 — cleanup + release prep (Kimi) — **queue complete**

**Kimi:** `.kimi-done` reports `GIT_HEAD=71c09b1`, `PYTEST=437 passed`, `UTCNOW_GREP=0`, broad catch count noted as intentional boundaries.

**Outcome:** Closed review findings from Phases 7–13 (utcnow adoption sweep, exception-narrowing cleanup, enriched failure-bundle population), plus release-prep artifacts: `.github/workflows/ci.yml`, `CONTRIBUTING.md`, `pyproject` license field, changelog update. Added docs: `phase-7-13-review-april-13.md`, `brainstorm-april-13.md`, and L09 loop spec.

**Git:** Merged `feature/phase-14-cleanup-release-prep` → `develop` (fast-forward to `71c09b1`). Queue through L09 complete; maintainer final pass + push/release next.

---

## 2026-04-12 — Loop: L08 Phase 13 — security audit CLI (Kimi) — **queue complete**

**Kimi:** ~16.8 min. `.kimi-done`: `GIT_HEAD=381a543`, **435 passed**.

**Outcome:** `hestia audit`, `hestia policy show`, tests added per §13.x.

**Git:** Merged `feature/phase-13-audit` → `develop`. **L01–L08** queue finished; Dylan: push + holistic review.

---

## 2026-04-12 — Loop: L07 Phase 12 — manual skills (Kimi)

**Kimi:** ~14.6 min. `.kimi-done`: `GIT_HEAD=12d7531`, **412 passed**.

**Outcome:** `skills/` package, `skill_store`, migration `c3d4e5f6g7h8_*`, `hestia skill` CLI group, **ADR-024**, `test_skills.py`.

**Git:** Merged `feature/phase-12-skills` → `develop`.

---

## 2026-04-12 — Loop: L06 Phase 11 — traces + failure bundles (Kimi)

**Kimi:** ~18.3 min. `.kimi-done`: `GIT_HEAD=20a5c40`, **386 passed**.

**Outcome:** `trace_store.py`, Alembic migration `b2c3d4e5f6g7_*`, orchestrator `finally` tracing, enriched `FailureBundle` fields, CLI wiring.

**Git:** Merged `feature/phase-11-trace-store` → `develop`.

---

## 2026-04-12 — Loop: L05 Phase 10 — memory epochs (Kimi)

**Kimi:** ~9.2 min. `.kimi-done`: `GIT_HEAD=2a54255`, **386 passed**.

**Outcome:** `memory/epochs.py`, CLI + `ContextBuilder` wiring, **ADR-023** under `docs/architecture/adr/`, `test_memory_epochs.py`.

**Git:** Merged `feature/phase-10-memory-epochs` → `develop`.

---

## 2026-04-12 — Loop: L04 Phase 9 — test infra (Kimi)

**Kimi:** `./scripts/kimi-run-current.sh` (~14.9 min). `.kimi-done`: `GIT_HEAD=39caca5`, **379 passed**.

**Outcome:** Matrix e2e scaffold (`tests/e2e/*`, docker-compose, mock llama), Telegram async tests expanded, **`tests/integration/test_cli_integration.py`**. E2E module **skipped by default** (Docker). Carry-forward into L05: baseline 379, keep default pytest green, epoch ordering vs identity.

**Git:** Merged `feature/phase-9-test-infra` → `develop`.

---

## 2026-04-12 — Loop: L03 Phase 8b — CLI, exceptions, datetime (Kimi + Cursor prep)

**Carry-forward set in `L03-phase-8b-cli-exceptions-datetime.md`:** README “personality” must match **compiled identity** (`IdentityConfig` / `IdentityCompiler`); finish roadmap **§8.4** and **§8.5**; note prior commits for §8.3, `PlatformError`, scheduler `_dt_gt_utc`.

**Kimi:** `./scripts/kimi-run-current.sh` (~13.7 min). `.kimi-done`: `GIT_HEAD=0034038`, `354 passed`.

**Outcome:** **`0034038`** — `core/clock.py`, `utcnow()` adoption, exception narrowing per roadmap table, README identity section updated (`IdentityConfig` example), scheduler/session/registry/telegram/slot tweaks, tests adjusted.

**Git:** Merged `feature/phase-8b-cli-exceptions-datetime` → `develop`. **Next:** **L04** (`KIMI_CURRENT` → `L04-phase-9-test-infra.md`); carry-forward added for aiosqlite warnings, `hestia matrix` smoke, Docker-skippable e2e, UTC in scheduler assertions.

---

## 2026-04-12 — Loop: L02 Phase 8a — identity + reasoning budget (Kimi)

**Commands:** `git checkout -b feature/phase-8a-identity-reasoning`, `./scripts/kimi-run-current.sh` (~12.3 min). `.kimi-done`: `GIT_HEAD=98b4caa`, `354 passed, 1 warning`.

**Outcome:** Commit **`98b4caa`** — `IdentityConfig`, `src/hestia/identity/compiler.py`, context builder integration, **`DefaultPolicyEngine.reasoning_budget()`**, orchestrator uses policy instead of hardcoded 2048, **ADR-022**, `tests/unit/test_identity_compiler.py`, policy tests extended. **354 passed** (known aiosqlite thread warnings unchanged).

**Git:** Merged `feature/phase-8a-identity-reasoning` → `develop`.

**Next:** L03 (`L03-phase-8b-cli-exceptions-datetime.md`).

---

## 2026-04-12 — Loop: L01 Matrix adapter (Kimi)

**Commands:** `git checkout -b feature/matrix-adapter` from `develop`, `./scripts/kimi-run-current.sh` (~21.6 min). `.kimi-done`: `GIT_HEAD=c3c34b2`, `PYTEST=328 passed`.

**Outcome:** `MatrixAdapter` (`matrix_adapter.py`), `MatrixConfig`, `hestia matrix` CLI, `matrix-nio` dependency, **ADR-021**, **19** new tests in `test_matrix_adapter.py`. Handoff: `docs/handoffs/L01-matrix-adapter.md`. **328 passed** locally after merge to `develop`.

**Git:** Merged `feature/matrix-adapter` → `develop` (fast-forward to `c3c34b2`).

**Next:** L02 Phase 8a (`KIMI_CURRENT.md` → `L02-phase-8a-identity-reasoning.md`).

---

## 2026-04-12 — Loop: Phase 7 cleanup (Kimi) + merge + orchestration recovery

**Commands:** `./scripts/kimi-run-current.sh >> .kimi-output.log 2>&1` on `feature/phase-7-cleanup` (~20.5 min wall time). Kimi wrote `.kimi-done` with `GIT_HEAD=265003b`, `PYTEST=309 passed in 33.23s`.

**Outcome:** Commit **`265003b`** implements all seven sections of `kimi-hestia-phase-7-cleanup.md` (orchestrator `tool_chain`, `db.py` imports, `list_dir` factory + sandboxing, CLI confirm handler dedupe, remove bare read/write exports, `http_get` SSRF + `test_http_get_ssrf.py`, remove `COMPRESSING`). **309 passed** locally after merge (vs 311 baseline — COMPRESSING tests removed).

**Git:** Kimi had branched `265003b` from **`e0c71c7`**, skipping two local orchestration commits (`5082255`, `a8b793a`). **Recovery:** `git checkout develop`, merged `feature/phase-7-cleanup` (fast-forward to `265003b`), **cherry-pick** `5082255` `a8b793a` onto `develop` → commits **`6c40e7f`**, **`53f490a`**. Resolved `docs/HANDOFF_STATE.md` stash conflict manually.

**Next pointer:** `KIMI_CURRENT.md` → **L01 Matrix** (`kimi-loops/L01-matrix-adapter.md` + `matrix-integration.md`). Branch to create: `feature/matrix-adapter`.

---

## 2026-04-12 — Orchestration wiring (no Kimi run yet)

**Context:** Quiet default for `scripts/kimi-run-current.sh`, `.kimi-done` contract, this log file created.

**Next:** Run `./scripts/kimi-run-current.sh` (optional: `> .kimi-output.log 2>&1`), then Cursor reviews and appends the next section above this one.
