# Kimi loop L09 — Phase 14 (cleanup + release prep)

## Review carry-forward

- **Test baseline:** **`435 passed`** on `develop` after L08 merge — keep unit/integration green.
- **Three open issues from Phase 7–13 review** (see `docs/development-process/reviews/phase-7-13-review-april-13.md`):
  1. `utcnow()` inconsistently adopted — many files still use `datetime.now()` or `datetime.utcnow()`.
  2. Remaining bare/broad `except Exception` catches in orchestrator and CLI.
  3. Enriched failure bundle fields (`request_summary`, `policy_snapshot`, `slot_snapshot`, `trace_id`) not populated by orchestrator.
- **Release prep items** identified in release readiness audit (April 13):
  - pyproject.toml missing `license` field.
  - No `CONTRIBUTING.md`.
  - No GitHub Actions CI workflow.
  - ADR files only partially present in `docs/adr/` (ADR-022 and ADR-024 exist; earlier ADRs referenced in DECISIONS.md but not as individual files).

**Branch:** `feature/phase-14-cleanup-release-prep` from latest `develop`.

---

## Scope

### Part A — Code cleanup (3 items)

#### A1. Adopt `utcnow()` everywhere

Grep the entire `src/hestia/` tree for `datetime.now()`, `datetime.utcnow()`, and any bare `datetime.now` usage. Replace every instance with:

```python
from hestia.core.clock import utcnow
```

Exceptions (do NOT replace):
- If a call explicitly needs local time (e.g., display formatting for the user) — add a comment explaining why.
- Third-party library calls that require a specific datetime interface.

After replacement, verify no `datetime.now` or `datetime.utcnow` remains in `src/` (tests may use them for mocking — that's fine, but prefer `utcnow` there too when practical).

**Test:** Add a test in `tests/unit/test_clock.py` (or extend existing) that verifies `utcnow()` returns a timezone-aware datetime with `tzinfo=timezone.utc`.

#### A2. Narrow exception catches

Find all `except Exception` and bare `except:` in `src/hestia/`. For each one:

1. Identify what exceptions the protected code can actually raise.
2. Replace with specific types. Common mappings:
   - httpx calls → `httpx.HTTPError`, `httpx.TimeoutException`, `httpx.ConnectError`
   - SQLAlchemy calls → `sqlalchemy.exc.OperationalError`, `sqlalchemy.exc.IntegrityError`
   - JSON parsing → `json.JSONDecodeError`
   - File I/O → `OSError`, `FileNotFoundError`, `PermissionError`
   - Tool dispatch → keep `Exception` if this is the outermost error boundary, but add a comment: `# Outermost boundary — intentionally broad`
3. If you genuinely need a broad catch (outermost error boundaries like the orchestrator's main try/except), keep `except Exception` but add a logging statement and a comment explaining why it's broad.

**Do NOT** change catches in test files.

#### A3. Populate enriched failure bundle fields

In `src/hestia/orchestrator/engine.py`, find the failure-recording path (the code that creates and stores `FailureBundle` records). Update it to populate:

- `request_summary`: First 200 characters of the user's message for this turn (truncate with `...` if longer).
- `policy_snapshot`: JSON-serialized dict of current policy state. At minimum include: `{"reasoning_budget": <value>, "turn_token_budget": <value>, "tool_filter_active": <bool>}`. Use the policy engine's methods to get these values.
- `slot_snapshot`: JSON-serialized dict: `{"slot_id": <session.slot_id or null>, "temperature": <session.temperature.value>, "slot_saved_path": <session.slot_saved_path or null>}`.
- `trace_id`: If a `TraceRecord` was created for this turn (it's created in the finally block), link its ID. If the trace record is created after the failure record, restructure so the trace is created first, or use a shared turn-level ID.

**Test:** Add a test in `tests/unit/` (or `tests/integration/`) that triggers a failure (e.g., inference timeout) and verifies all four fields are non-None in the resulting `FailureBundle`.

---

### Part B — Release prep (4 items)

#### B1. Add license field to pyproject.toml

In `pyproject.toml` under `[project]`, add:

```toml
license = "Apache-2.0"
```

Place it after the `authors` field.

#### B2. Create CONTRIBUTING.md

Create `CONTRIBUTING.md` in the repo root. Keep it concise — under 80 lines. Include:

1. **Quick start**: `uv sync && uv run pytest tests/unit/ tests/integration/ -q`
2. **Code style**: Ruff for linting/formatting, mypy for types. Run `uv run ruff check src/` and `uv run mypy src/hestia/` before submitting.
3. **Branch model**: Feature branches from `develop`, PRs into `develop`, `main` for releases. Use gitflow naming: `feature/*`, `release/*`, `hotfix/*`.
4. **Testing**: All new code needs tests. Run `uv run pytest tests/unit/ tests/integration/ -q`. Use `pytest-asyncio` for async tests.
5. **Commit messages**: Conventional commits preferred (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`).
6. **Reporting bugs**: Open a GitHub issue with reproduction steps, expected vs actual behavior, and system info (Python version, GPU, llama.cpp version).
7. **Design decisions**: Major changes should have an ADR in `docs/adr/`. Read `docs/DECISIONS.md` for existing decisions.

Do NOT include a code of conduct (that's a separate decision for the maintainer). Do NOT include CLA language.

#### B3. Create GitHub Actions CI workflow

Create `.github/workflows/ci.yml` that runs on push to `develop` and `main`, and on all pull requests:

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v4
      - name: Set up Python ${{ matrix.python-version }}
        run: uv python install ${{ matrix.python-version }}
      - name: Install dependencies
        run: uv sync
      - name: Lint
        run: uv run ruff check src/
      - name: Type check
        run: uv run mypy src/hestia/ || true  # non-blocking until pre-existing errors fixed
      - name: Test
        run: uv run pytest tests/unit/ tests/integration/ -q
```

Notes:
- mypy is `|| true` because there are pre-existing type errors. Remove `|| true` once they're fixed.
- Only runs unit and integration tests — e2e tests need a real llama.cpp server and aren't suitable for CI.
- Uses `astral-sh/setup-uv` for fast uv installation.

#### B4. Update CHANGELOG.md

Add a new version section for `v0.1.0` (move items from `[Unreleased]` as appropriate). Include the Phase 7–13 work and this cleanup pass. Keep the `[Unreleased]` section empty for future work.

---

## Completion

1. `uv run pytest tests/unit/ tests/integration/ -q` — green.
2. `uv run ruff check src/` — clean on touched files.
3. Commit all changes with message: `fix: phase 14 cleanup + release prep`
4. `git push`
5. Write **`.kimi-done`**:

```text
HESTIA_KIMI_DONE=1
SPEC=docs/development-process/kimi-loops/L09-phase-14-cleanup-release-prep.md
BRANCH=feature/phase-14-cleanup-release-prep
PYTEST=<last line of pytest -q>
GIT_HEAD=<git rev-parse HEAD>
UTCNOW_GREP=<count of remaining datetime.now/utcnow in src/>
BROAD_EXCEPT_COUNT=<count of remaining broad catches, with comment if intentional>
```

6. Do **not** commit `.kimi-done`.
