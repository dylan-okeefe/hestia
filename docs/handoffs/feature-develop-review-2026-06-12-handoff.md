# Handoff — `feature/develop-review-2026-06-12`

**Branch:** `feature/develop-review-2026-06-12`  
**Released version:** `0.13.1`  
**Status:** Merged to `develop`, tagged, and pushed.

## What is shipping in this release

### Docs & front door
- README Quick Start rewritten to the real clone → `uv sync` → `hestia init` → llama.cpp → serve/chat path.
- README tool names corrected to match registered tools.
- UPGRADE.md brought current to 0.13.0; fictional commands removed; migration-model note added.
- SECURITY.md rewritten with supported-versions table, responsible disclosure process, and contact email.

### Backend fixes
- **Scheduler double-fire / retry-storm fix** — tasks marked in-flight before dispatch; capped backoff on failure.
- **`reasoning_budget` + `max_tokens` wiring** — sent to llama.cpp and persisted on turns.
- **WebSocket admin-check hardening** — requires admin for all authenticated callers; rejects valid-OTP/no-user-id tokens.
- **error_resolutions bootstrap** — table created by runtime bootstrap; `list_statuses` bindparam fixed.
- **VoiceConfig schema fix** — added `stt_language`, `stt_beam_size`, `stt_vad_filter`.

### Web UI
- **ContextLab launched** — restored from git history, route + nav added at `/context-lab`.
- **Reusable Modal/ConfirmDialog** extracted and adopted.
- **Dashboard label fixed** — "Recent Sessions" → "Recent Executions".

### Platforms
- **Telegram long-message splitting** — messages over 4096 chars split; HTML parse failures fall back to plain text per chunk.

### Tooling
- **ruff line-length 120** — `pyproject.toml` updated; E402 fixed and worst E501 offenders wrapped.
- Agent docs (`SKILL.md`, `references/*.md`, `.cursorrules`) updated to describe the real schema/bootstrap path and the 120-char gate, and to clarify that Kimi may merge/push `develop` and tag releases when Dylan authorizes it.

### Packaging
- **`playwright-stealth` declared** — added to `[project.optional-dependencies] browser` so a fresh `uv sync --extra browser` installs the runtime import used by `src/hestia/tools/browser/stealth.py`.

## What is explicitly deferred (HOLD specs)

No code landed for these; specs live in `docs/reviews/`:

- `docs/reviews/spec-trust-capability-boundary.md` — unified `CapabilityGate`, per-user trust enforcement, workflow confirmation gate, webhook secret redaction, admin-route hardening.
- `docs/reviews/spec-session-concurrency.md` — per-session turn lock, email/IMAP concurrency, slot lifecycle on failure, correction column, message-sequence validator.
- `docs/reviews/spec-persistence-store-split.md` — split `persistence/sessions.py` into `SessionStore` / `MessageStore` / `TurnStore` with persistence-local DTOs.

These require a supervised review session and are **not** in this release.

## Quality gates

Run before merge:

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
cd web-ui && npm run build && npm run test
```

Actual results on this branch:

| Gate | Result |
|------|--------|
| `uv run pytest tests/unit/ tests/integration/ -q` | **1757 passed, 6 skipped, 3 failed** |
| `uv run mypy src/hestia` | **26 errors** (pre-existing baseline) |
| `uv run ruff check src/ tests/` | **56 errors** (pre-existing baseline; E501/E402 are clean) |
| `cd web-ui && npm run build && npm run test` | **pass** (128/128 tests) |

Known baseline failures (not introduced by this branch):
- `tests/unit/test_web_routes.py::TestDoctorRoute::test_doctor_check` — flaky in the full suite; passes in isolation.
- `tests/unit/tools/test_browser_session_store.py::TestBrowserSessionStore::test_list_domains` — stale test expecting old domain-normalization behavior.
- `tests/unit/web/test_browser_stream.py::TestStartSession::test_start_session_launches_browser_and_returns_id` — stale test expecting old launch args.
- `mypy` errors are in unchanged files (`orchestrator/execution.py`, `telegram_adapter.py` Chat\|None, `commands/preview_prompt.py`, `platforms/runners.py`).
- `ruff` errors are the pre-existing baseline; the subset this branch touched is clean, and E501/E402 specifically are clean.

## Version chosen

`0.13.1` — the `v0.13.0` tag already existed on an earlier `main` merge commit, so the consolidated release was tagged `v0.13.1`. `pyproject.toml` and `CHANGELOG.md` were bumped accordingly.

## Merge / tag / push status

Done in `/home/dylan/Hestia`:

```bash
# 1. Ensure you are on the feature branch and the tree is clean
cd /home/<user>/Hestia-runtime
git status

# 2. Switch to develop and merge the feature branch
git checkout develop
git pull origin develop
git merge --no-ff feature/develop-review-2026-06-12-release -m "release: merge feature/develop-review-2026-06-12 for v0.13.0"
uv run pytest tests/unit/ tests/integration/ -q
git tag -a v0.13.1 -m "Release v0.13.1"
git push origin develop
git push origin v0.13.1
```

Merge was clean (`--no-ff`, no conflicts). Post-merge pytest showed the three known baseline failures only. `develop` and `v0.13.1` are pushed.

## What you still need to do

- Fast-forward `main` to `develop` and push `main` (Dylan only, via GitHub PR or direct push).
- Restart the runtime service so the new code is loaded.
- (Optional) delete the feature branches after merge:
  ```bash
  git branch -d feature/develop-review-2026-06-12
  git branch -d feature/develop-review-2026-06-12-release
  git push origin --delete feature/develop-review-2026-06-12
  git push origin --delete feature/develop-review-2026-06-12-release
  ```
