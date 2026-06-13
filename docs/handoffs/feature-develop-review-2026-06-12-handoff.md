# Handoff — `feature/develop-review-2026-06-12`

**Branch:** `feature/develop-review-2026-06-12`  
**Target version:** `0.13.0`  
**Status:** Ready for final merge/tag/push.

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
- Agent docs (`SKILL.md`, `references/*.md`, `.cursorrules`) updated to describe the real schema/bootstrap path and the 120-char gate.

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

Known baseline:
- `tests/unit/test_web_routes.py::TestDoctorRoute::test_doctor_check` is flaky in the full suite but passes in isolation.
- `tests/unit/tools/test_browser_session_store.py::TestBrowserSessionStore::test_list_domains` is a stale test expecting old domain-normalization behavior.
- `tests/unit/web/test_browser_stream.py::TestStartSession::test_start_session_launches_browser_and_returns_id` is a stale test expecting old launch args.
- `mypy` has 26 pre-existing errors (down from 31); none are in code changed by this branch.

## Version chosen

`0.13.0` — the CHANGELOG already staged 0.13.0 with a 2026-06-06 date; this branch completes that release and updates the date to 2026-06-13. `pyproject.toml` was bumped from `0.12.2` to `0.13.0` to match.

## Merge / tag / push commands

```bash
# 1. Ensure you are on the feature branch and the tree is clean
cd /home/dylan/Hestia-runtime
git status

# 2. Switch to develop and merge the feature branch
git checkout develop
git pull origin develop
git merge --no-ff feature/develop-review-2026-06-12 -m "release: merge feature/develop-review-2026-06-12 for v0.13.0"

# 3. Tag the release
git tag -a v0.13.0 -m "Release v0.13.0"

# 4. Push develop and the tag
git push origin develop
git push origin v0.13.0

# 5. (Optional) delete the feature branch after merge
git branch -d feature/develop-review-2026-06-12
git push origin --delete feature/develop-review-2026-06-12
```

After push, restart the runtime service so the new code is loaded.
