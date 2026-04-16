# Kimi loop L18 — Post-public cleanup + v0.2.1 release

## Review carry-forward

- L17 (release v0.2.0) is fully complete on `develop` and `main`. `v0.2.0` tag and `development-history-snapshot` tag are pushed.
- `KIMI_CURRENT.md` still says "L17 queued" — stale; will be updated by §3 of this loop (pointer moves with the rest of the orchestration docs).
- 44 pre-existing mypy errors across 12 files. Not in scope to fix all of them; this loop just makes the situation honest in CI (see §4).

**Branch:** `feature/l18-post-public-cleanup` from **`develop`**.

---

## Goal

Address the second-round pre-public review:

1. Fix the SecurityAuditor `memory_write` → `save_memory` tool-name bug (silent dead code).
2. Make per-artifact metadata writes atomic (consistency with the inline index fix from L15).
3. Move internal AI-orchestration docs out of the public `docs/` tree into a clearly labeled `docs/development-process/` directory with an explanatory README.
4. Make CI mypy honest: capture the baseline error count, document it, leave `|| true` in place with a comment that points at the baseline file. Optionally remove the misleading `disallow_untyped_defs = true` from `pyproject.toml`.
5. Cut a `v0.2.1` patch release with all of the above plus the L17 cleanup that was added during L17 itself.

After this loop, the repo is genuinely "public-clean" — a visitor opening `docs/` will not find `KIMI_CURRENT.md` next to `architecture.md` and wonder what it is.

---

## §-1 — Create branch

```bash
git checkout develop
git pull origin develop
git checkout -b feature/l18-post-public-cleanup
```

Confirm clean working tree and that `git log -1 --oneline` is **`5c42a0e docs: point KIMI_CURRENT at L17 release v0.2.0`** or later (the L17 release commits are on `main`, not `develop`; that is intentional).

Run baseline tests and record the count:
```bash
uv run pytest tests/unit/ tests/integration/ -q
```
Expected: **474 passed, 6 skipped** (or higher).

---

## §1 — Fix SecurityAuditor `save_memory` tool-name bug

**File:** `src/hestia/audit/checks.py`

### Problem

The trace-pattern check at line 479 looks for `tool == "memory_write"`, but the actual tool name registered in `src/hestia/tools/builtin/memory_tools.py` is `save_memory`. The "memory write after http_get" suspicious-pattern detection therefore never fires on real data. The accompanying test in `tests/unit/test_audit.py` uses the same wrong name, so both sides of the bug are consistently wrong and there is nothing to flag the regression.

### Fix

In `src/hestia/audit/checks.py`, rename **all** occurrences of `memory_write` to `save_memory` in the trace-pattern detection block (lines ~464–501). Do **not** rename the local variable names that include `memory_write` if they describe a behavior — but for consistency, use `save_memory_after_http` style names. Specifically:

- Line 464 `memory_write_after_http = 0` → `save_memory_after_http = 0`
- Line 471 comment `# Pattern: memory_write after http_get …` → `# Pattern: save_memory after http_get …`
- Line 473 `has_memory_write_after_http = False` → `has_save_memory_after_http = False`
- Line 479 `elif tool == "memory_write" and has_http:` → `elif tool == "save_memory" and has_http:`
- Line 480 `has_memory_write_after_http = True` → `has_save_memory_after_http = True`
- Lines 484–501 update all uses of `memory_write_after_http` and `has_memory_write_after_http`.
- Finding messages on lines 494 and 501 should read `save_memory after http_get` (not `memory_write after http_get`).

### Tests

**File:** `tests/unit/test_audit.py`

Find the test that currently does `tools_called = ["http_get", "memory_write"]` (or similar). Update it to use `["http_get", "save_memory"]`. The test should still pass after the fix.

Add a **regression test** that uses the *real* registered tool name and asserts the warning fires:

```python
def test_audit_detects_save_memory_after_http_in_trace():
    """The trace-pattern check must use the real tool name (save_memory),
    not a stale alias (memory_write)."""
    # … construct a fake trace with tools_called = ["http_get", "save_memory"]
    # run the auditor's trace check
    # assert there is a "warning" finding about "save_memory after http_get"
```

If you also want to assert the *negative* (the wrong-name path no longer fires), add a second test that confirms `["http_get", "memory_write"]` produces **no** finding (because `memory_write` is not a real tool).

### Search the rest of the codebase

Run `grep -rn '"memory_write"\|''memory_write''' src/ tests/` and review every hit. The other files containing `memory_write` are documentation/historical (CHANGELOG, DECISIONS, design notes, README, deferred-roadmap). For each, decide:
- **Doc files**: leave as-is unless they describe a real tool (in which case fix). The capability constant `MEMORY_WRITE` in `src/hestia/tools/capabilities.py` is **not** the same thing — it is a capability label, not a tool name. Do not rename it.
- **`README.md`**: if the README describes `memory_write` as a tool, fix it to `save_memory`. If it only mentions the `memory_write` capability, leave it.
- **`docs/DECISIONS.md`**, **`docs/roadmap/future-systems-deferred-roadmap.md`**, **`docs/design/hestia-phase-8-plus-roadmap.md`**: historical documents — only correct references that describe the implemented code, not future-design references.

**Commit:** `fix(audit): use real tool name save_memory in trace-pattern check`

---

## §2 — Atomic per-artifact metadata write

**File:** `src/hestia/artifacts/store.py`

### Problem

L15 made `_save_inline_index()` atomic via `tempfile.mkstemp()` + `os.replace()`. But the per-artifact metadata write at line 154 (`with open(metadata_path, "w") as f: json.dump(asdict(metadata), f)`) is still a plain truncate-and-write. A crash mid-write corrupts that artifact's metadata file, and `fetch_metadata()` will then raise `JSONDecodeError` instead of `ArtifactNotFoundError`.

### Fix

Refactor into a small private helper, since the same atomic pattern will now apply in two places:

```python
def _atomic_write_json(self, path: Path, data: dict) -> None:
    """Write JSON to disk atomically: temp file in same dir + os.replace().

    Prevents corruption if the process crashes mid-write.
    """
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise
```

Replace **both** `_save_inline_index()` and the per-artifact metadata write at line 154 to use this helper. This deduplicates the atomic logic.

### Tests

**File:** `tests/unit/test_artifacts.py`

Add a test that the per-artifact metadata file is atomically written:

```python
def test_per_artifact_metadata_atomic_write(tmp_path):
    """The {handle}.json metadata file must be written atomically."""
    # store an artifact, capture its metadata path
    # mock json.dump to raise mid-write
    # confirm the original metadata (or no file) is left, never a partial file
```

You can model this on the existing `test_inline_index_atomic_write` / `test_inline_index_survives_crash` tests added in L15.

**Commit:** `fix: atomic write for per-artifact metadata, dedupe with shared helper`

---

## §3 — Move internal AI-orchestration docs to `docs/development-process/`

### Decision rationale

Two options were considered: delete entirely vs. move-with-README. Hestia is explicitly built using a Cursor + Kimi + human workflow, and the AI-assisted development story is on-brand. Move-and-label preserves the historical record, removes the "what is `KIMI_CURRENT.md`?" confusion, and signals the project's transparency about its build process.

### Files to move

From `docs/orchestration/`:
- `kimi-loop-log.md`
- `kimi-phase-queue.md`
- `kimi-loops/` (whole directory: `L01-…` through `L18-…`)
- `runtime-feature-testing.md` — **stays in `docs/`**, this is operator documentation, not AI process. Move it to `docs/testing/runtime-feature-testing.md` or just leave it in `docs/runtime-feature-testing.md`.

From `docs/prompts/`:
- All `KIMI_*.md` files (`KIMI_CURRENT.md`, `KIMI_LOOPS_L10_L14.md`, `KIMI_PHASE_*.md`, etc.)

From `docs/design/`:
- `kimi-hestia-phase-7-cleanup.md` — Kimi prompt artifact, move
- `brainstorm-april-13.md` — internal brainstorm, move

From `docs/reviews/`:
- `phase-7-13-review-april-13.md` — internal review session, move
- The whole `docs/reviews/` directory only contains this one file, so move the file and `rmdir` the empty parent.

### Where to move them

Create `docs/development-process/` with this structure:

```
docs/development-process/
├── README.md                           # NEW — explains the directory
├── kimi-loop-log.md                    # from docs/orchestration/
├── kimi-phase-queue.md                 # from docs/orchestration/
├── kimi-loops/                         # from docs/orchestration/kimi-loops/
│   └── L01-…L18-….md
├── prompts/                            # from docs/prompts/
│   └── KIMI_*.md (all of them)
├── design-artifacts/                   # NEW subdir
│   ├── kimi-hestia-phase-7-cleanup.md  # from docs/design/
│   └── brainstorm-april-13.md          # from docs/design/
└── reviews/                            # from docs/reviews/
    └── phase-7-13-review-april-13.md
```

### `docs/development-process/README.md` content

Write a ~40-line README that:
1. Names the directory and explains it is **historical**, not current operating documentation.
2. Briefly describes the Cursor + Kimi + human workflow.
3. Links to the two persistent design ADRs (`docs/adr/`) for the actual current architecture.
4. Mentions that loop specs (`kimi-loops/L*.md`) are immutable historical artifacts of how each phase was scoped and reviewed.
5. Notes that the older handoff state files were archived **out of repo** in L16 (do not link to vault path; just say "to a private archive outside this repository").

Suggested content:

```markdown
# Development Process Archive

This directory contains the operational records of how Hestia was built using an
AI-assisted workflow. **It is historical**, not current operating documentation.
For current architecture, see [`../adr/`](../adr/) and [`../README.md`](../README.md).

## The build workflow

Hestia was built incrementally using a three-tool loop:

- **Cursor** (or Claude/Cowork) — code review, prompt authoring, per-loop merge
  decisions and orchestration.
- **Kimi** — autonomous executor. Reads a single loop spec (`kimi-loops/L*.md`),
  implements every section, runs tests, commits, signals completion via a
  `.kimi-done` artifact.
- **Dylan (human)** — direction, secrets, final pass before public push and
  release tagging.

Each numbered loop (L01–L18) corresponds to one focused work session: a single
spec file, a single feature branch, a single merge to `develop` after green
review. After ~16 such loops the project reached `v0.2.0` (first public
release); the patch loop `L18` produced `v0.2.1`.

## What's here

| Path | What |
|------|------|
| `kimi-loops/L*.md` | One spec per loop. Names the sections to implement, sketches code, lists tests, and defines the `.kimi-done` contract. Immutable once the loop is merged. |
| `kimi-phase-queue.md` | Top-level ordering of all loops. |
| `kimi-loop-log.md` | Per-loop narrative: what Kimi did, what Cursor reviewed, what was merged. Newest entries at the top. |
| `prompts/KIMI_*.md` | Earlier prompt formats (pre-loop-spec era), kept for reference. |
| `design-artifacts/`, `reviews/` | One-off design and review notes from the build. |

Older per-phase handoff reports (Phase 1a–L15) were archived to a private
location outside this repository during L16.

## Why keep this in the public repo?

Transparency about how the project was built — which models, which workflow,
how much was AI-driven vs. human-driven, where the failure modes were. Anyone
trying to reproduce the methodology has the full record.

If you are only interested in *using* Hestia, ignore this directory entirely.
```

### How to actually do the move

Use `git mv` so history is preserved:

```bash
mkdir -p docs/development-process/kimi-loops
mkdir -p docs/development-process/prompts
mkdir -p docs/development-process/design-artifacts
mkdir -p docs/development-process/reviews

git mv docs/orchestration/kimi-loop-log.md   docs/development-process/
git mv docs/orchestration/kimi-phase-queue.md docs/development-process/
git mv docs/orchestration/kimi-loops/*       docs/development-process/kimi-loops/
git mv docs/orchestration/runtime-feature-testing.md docs/runtime-feature-testing.md

git mv docs/prompts/*.md   docs/development-process/prompts/

git mv docs/design/kimi-hestia-phase-7-cleanup.md docs/development-process/design-artifacts/
git mv docs/design/brainstorm-april-13.md         docs/development-process/design-artifacts/

git mv docs/reviews/phase-7-13-review-april-13.md docs/development-process/reviews/

# Remove empty parent dirs
rmdir docs/orchestration/kimi-loops 2>/dev/null
rmdir docs/orchestration         2>/dev/null
rmdir docs/prompts               2>/dev/null
rmdir docs/reviews               2>/dev/null
```

Then **write** the new `docs/development-process/README.md` with the content sketched above.

### Update internal cross-references

After the move, run a search for stale paths and fix every link:

```bash
rg -l 'docs/orchestration/|docs/prompts/|docs/reviews/|docs/design/kimi-hestia-phase-7-cleanup\.md|docs/design/brainstorm-april-13\.md' .
```

Update or remove every reference in:
- `docs/HANDOFF_STATE.md` — file is **gone** (deleted in L16). If any other doc still links to it, leave the broken link or note it; do not recreate the file.
- `docs/development-process/kimi-phase-queue.md` itself — paths in its tables now need updating to `kimi-loops/L*.md` (relative to its new location, paths inside the dir are unchanged).
- `docs/development-process/kimi-loops/L*.md` — many of these reference each other. Since they all moved together, intra-directory paths still work. Fix only the ones that reference *external* paths (e.g. `../HANDOFF_STATE.md`, `../../scripts/kimi-run-current.sh`).
- `scripts/kimi-run-current.sh` — references `docs/prompts/KIMI_CURRENT.md`. Update to `docs/development-process/prompts/KIMI_CURRENT.md` **or** delete the script (it is itself an internal-process tool; consider moving it to `docs/development-process/scripts/`).
- `.cursorrules` — references `docs/HANDOFF_STATE.md`, `docs/orchestration/kimi-phase-queue.md`, `docs/prompts/KIMI_CURRENT.md`, `docs/orchestration/kimi-loops/`, etc. Update all paths.
- `.cursor/rules/*.mdc` if any exist — check and update.
- `README.md` — should not reference any of these paths directly. Verify with grep.
- `CHANGELOG.md` — may have changelog entries that reference loop specs by old path; update or leave (changelog history is immutable in spirit).

### Move `KIMI_CURRENT.md` to "no active loop"

`docs/development-process/prompts/KIMI_CURRENT.md` should be replaced (or have its content updated) to:

```markdown
# Kimi — current task

**Status:** Idle. The last loop (L18) shipped `v0.2.1`.

This file is the orchestration pointer used during active development cycles.
When idle (no loop in flight), it contains only this notice. See
[`../kimi-loop-log.md`](../kimi-loop-log.md) for the historical record.

If you are restarting Kimi-driven development, write a new loop spec in
[`../kimi-loops/`](../kimi-loops/) and update this file to point at it.
```

### Update the script (if kept in `scripts/`)

`scripts/kimi-run-current.sh` line 14 contains the path `docs/prompts/KIMI_CURRENT.md`. Update to `docs/development-process/prompts/KIMI_CURRENT.md`. Or move the script to `docs/development-process/scripts/kimi-run-current.sh` and update the `.cursorrules` reference accordingly. Either is fine; pick the one with fewer downstream changes.

### Tests

No test changes — this is a docs-and-paths-only section. After all moves:

```bash
uv run pytest tests/unit/ tests/integration/ -q   # must still match baseline
```

**Commit:** `docs: archive AI development process to docs/development-process/`

---

## §4 — Make CI mypy honest

**File:** `.github/workflows/ci.yml`

### Problem

The current step is:

```yaml
- name: Type check
  run: uv run mypy src/hestia/ || true  # non-blocking until pre-existing errors fixed
```

There are 44 pre-existing errors across 12 files. The `disallow_untyped_defs = true` setting in `pyproject.toml` is decorative under this configuration. The reviewer flagged this as low priority but worth being honest about.

### Fix (chosen approach: capture baseline, keep non-blocking, document explicitly)

1. Generate the current mypy baseline:

   ```bash
   uv run mypy src/hestia/ 2>&1 | grep "error:" > docs/development-process/mypy-baseline.txt || true
   wc -l docs/development-process/mypy-baseline.txt    # should be 44
   ```

   Commit this file. It is the snapshot of known errors as of v0.2.1.

2. Update `.github/workflows/ci.yml` to compare against the baseline (no new errors allowed):

   ```yaml
   - name: Type check (allows pre-existing errors, blocks new ones)
     run: |
       uv run mypy src/hestia/ 2>&1 | grep "error:" | sort > /tmp/mypy-current.txt || true
       sort docs/development-process/mypy-baseline.txt > /tmp/mypy-baseline.txt
       if ! diff -q /tmp/mypy-baseline.txt /tmp/mypy-current.txt > /dev/null; then
         echo "::error::mypy errors changed from baseline"
         echo "--- diff ---"
         diff /tmp/mypy-baseline.txt /tmp/mypy-current.txt || true
         exit 1
       fi
   ```

   This makes the step **fail** if any *new* mypy error is introduced, while still accepting the existing 44.

3. Add a short note in `docs/development-process/README.md` (or a separate `MYPY.md` next to the baseline) explaining the file:

   > `mypy-baseline.txt` lists the 44 pre-existing mypy errors as of v0.2.1.
   > CI fails on any *new* error. To fix one of these baseline errors, fix it in
   > the source and remove the matching line from the baseline in the same commit.

If the diff approach is too brittle (line numbers shift on edits), an alternative is to count errors and fail if the count grows. The diff approach is cleaner for catching specific regressions; the count approach is more tolerant of line-number drift. Pick one — **count-based is acceptable** if implementing the diff cleanly proves fiddly:

```yaml
- name: Type check (count must not increase)
  run: |
    BASELINE=$(wc -l < docs/development-process/mypy-baseline.txt)
    CURRENT=$(uv run mypy src/hestia/ 2>&1 | grep -c "error:" || true)
    echo "mypy baseline: $BASELINE, current: $CURRENT"
    if [ "$CURRENT" -gt "$BASELINE" ]; then
      echo "::error::mypy errors increased from $BASELINE to $CURRENT"
      exit 1
    fi
```

Use the **count-based** version if you are not confident the diff version will be stable. Document whichever you choose in the README note.

### Optional: tighten `pyproject.toml`

Leave `disallow_untyped_defs = true` in `pyproject.toml` (it is the right long-term goal). Add a comment above the mypy section noting that 44 errors are baselined in `docs/development-process/mypy-baseline.txt`.

### Tests

CI-only change. No pytest tests. Run mypy locally to confirm the count and that the diff/count step would not fail:

```bash
uv run mypy src/hestia/ 2>&1 | grep -c "error:"   # should equal baseline count
```

**Commit:** `ci: baseline mypy errors, fail on new ones (44 pre-existing)`

---

## §5 — CHANGELOG and version bump for v0.2.1

**Files:** `CHANGELOG.md`, `pyproject.toml`, `uv.lock`.

### CHANGELOG.md

Add a new section at the top (above `[0.2.0]`):

```markdown
## [0.2.1] — 2026-04-15

### Fixed
- `SecurityAuditor` trace-pattern check now uses the real tool name `save_memory`
  instead of the stale alias `memory_write`. The "save_memory after http_get"
  warning previously never fired on real data.
- `ArtifactStore` per-artifact metadata writes are now atomic
  (`tempfile.mkstemp` + `os.replace`), matching the inline-index fix from v0.2.0.

### Changed
- AI-orchestration documentation (`docs/orchestration/`, `docs/prompts/`, internal
  reviews and brainstorms) moved to `docs/development-process/` with an
  explanatory README. The public `docs/` tree now contains only user-facing
  documentation, ADRs, and operator runbooks.
- CI mypy step is now baseline-aware: 44 pre-existing errors are recorded in
  `docs/development-process/mypy-baseline.txt`; new errors fail CI.
```

### pyproject.toml

Bump `version = "0.2.0"` to `version = "0.2.1"`.

### uv.lock

Run `uv sync` to update `uv.lock`.

### Commit

```bash
git add CHANGELOG.md pyproject.toml uv.lock
git commit -m "chore: prep v0.2.1 release"
```

---

## §6 — Promote `develop` → `main`, tag `v0.2.1`, push

This mirrors L17's Phase 4 + Phase 5 but for a patch release.

### 6a. Final test pass on develop

```bash
git checkout feature/l18-post-public-cleanup   # if not already
uv run pytest tests/unit/ tests/integration/ -q
```

Must match or exceed the §-1 baseline (474 passed minimum).

### 6b. Merge feature branch into develop

```bash
git checkout develop
git merge --no-ff feature/l18-post-public-cleanup -m "Merge L18 — post-public cleanup + v0.2.1 prep"
git push origin develop
```

### 6c. Promote develop into main

```bash
git checkout main
git pull origin main
git merge --no-ff develop -m "Release v0.2.1

Patch release.

- Fix SecurityAuditor save_memory tool-name bug
- Atomic per-artifact metadata writes
- Move AI-orchestration docs to docs/development-process/
- Baseline-aware mypy in CI

See CHANGELOG.md for the full list."
```

### 6d. Tag v0.2.1

```bash
git tag -a v0.2.1 -m "Hestia v0.2.1 — patch release

Bug fix (SecurityAuditor tool name), atomicity polish, public-tree
cleanup, baseline-aware CI mypy. See CHANGELOG.md."
```

### 6e. Push everything

```bash
git push origin main
git push origin v0.2.1
```

### 6f. Confirm final state

```bash
git log -1 --oneline main
git log -1 --oneline develop
git tag -l | sort
```

Expected tags include `v0.0.0`, `v0.1.0`, `v0.2.0`, `v0.2.1`, `development-history-snapshot`.

`main` and `develop` should both be at (or have) the v0.2.1 merge commit.

---

## §7 — Branch cleanup

```bash
git branch -d feature/l18-post-public-cleanup
git push origin --delete feature/l18-post-public-cleanup 2>/dev/null || true   # may not exist on origin
git remote prune origin
```

Final test pass on both branches:

```bash
git checkout main
uv run pytest tests/unit/ tests/integration/ -q
git checkout develop
uv run pytest tests/unit/ tests/integration/ -q
```

Both must match the §-1 baseline.

---

## Handoff

Write `.kimi-done` (do **not** commit it):

```text
HESTIA_KIMI_DONE=1
SPEC=docs/development-process/kimi-loops/L18-post-public-cleanup-v0.2.1.md
LOOP=L18
BRANCH=develop
PYTEST_BASELINE=<count from §-1>
PYTEST_FINAL_DEVELOP=<count from §7>
PYTEST_FINAL_MAIN=<count from §7>
GIT_HEAD_DEVELOP=<git rev-parse develop>
GIT_HEAD_MAIN=<git rev-parse main>
TAG_V021=<git rev-parse v0.2.1>
SAVE_MEMORY_FIX=done
ATOMIC_METADATA=done
DOCS_MOVED=docs/development-process/
MYPY_BASELINE_LINES=<wc -l of mypy-baseline.txt>
```

(Note that the spec path in `SPEC=` reflects the new location after §3's move.)

---

## Critical rules recap

1. **No secrets in code.**
2. **One commit per section** with the message shown above.
3. **Run `uv run pytest tests/unit/ tests/integration/ -q`** after every commit. All must pass.
4. **Run `uv run ruff check src/ tests/`** — fix any *new* violations introduced by this loop. Pre-existing ruff debt is out of scope.
5. **§3 is the riskiest section** — many cross-references. After moving, grep for every old path and confirm no broken links remain in actively-rendered docs (README, CHANGELOG, ADRs).
6. **Do not modify `v0.2.0` history.** All changes are additive on top of `develop`.
7. **`.kimi-done` is the signal.** Write it last, after every section is committed and pushed.
8. **Stop and report immediately if any phase fails.** Especially §6 (release) — destructive operations (tag push, main merge) only run after all earlier sections succeed.
