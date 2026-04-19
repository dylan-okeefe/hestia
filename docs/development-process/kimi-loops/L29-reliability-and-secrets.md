# Kimi loop L29 — reliability surface, secrets hygiene, stale docs

## Review carry-forward

From **L28 review (Cursor, 2026-04-18, merged as `dcc54c5`):**

- L28 shipped clean (673 passed / 6 skipped / 0 mypy). No L28 blockers.
- **Pre-existing ruff debt: 243 errors** in `src/hestia` + `tests` on `develop` after L28 (was 245 before; L28 incidentally fixed 2). Non-blocking for L29, but **do not introduce new ruff errors** — `uv run ruff check src/hestia tests` count must be ≤ 243 at the end of L29.
- New test-count baseline: **673 passed / 6 skipped**. Subsequent loops must hold or exceed.
- Coverage gap noted at L28 review (soft target — implement only if it falls naturally out of an L29 section): integration test for `delete_memory` confirmation flow on Telegram/Matrix adapters.
- Lockfile hygiene held this loop. Continue: `uv lock` in the same logical commit as any version bump.

From **external review (2026-04-18)** — verified against `develop` after L28 lands:

- Reflection scheduler (`src/hestia/reflection/scheduler.py:63`) and runner (`reflection/runner.py:118,146`) **swallow** all inference errors with `except Exception: logger.exception(...)` and return empty lists. Same pattern in style scheduler (`src/hestia/style/scheduler.py:57`). Worst failure mode for a personal assistant: feature dies silently at 3am. Need a **failure ring buffer** surfaced via CLI.
- `SOUL.md` and `docs/calibration.json` are loaded with **CWD-relative paths** that silently degrade to defaults if missing. A user running `hestia chat` from `~` (without installing under repo root) gets no personality and no calibration with **no warning**.
- `EmailConfig.password` is plaintext Python in user config. No `password_env` field, no env-var fallback. Anyone who pastes their config to GitHub leaks credentials. Add an env-var path and document it loudly.
- `WebSearchConfig.provider` docstring (`src/hestia/config.py:319`) advertises `"tavily" | "brave" | ""` but the factory raises `ValueError` for `"brave"`. Either implement Brave (out of scope) or **remove `"brave"` from the type hint and docs**.
- `SECURITY.md` lists only `0.5.x` as supported (we're on `0.7.2` after L28). Doesn't mention `TrustConfig`, the egress audit log, the injection scanner. Disclosure line says "see repository owner's profile" — vague.
- ADRs are split between `docs/adr/` (ADR-0019, 022, 024) and `docs/development-process/decisions/` (ADR-0014, 0015, 0017, 0018). `CONTRIBUTING.md` points at `docs/adr/`. Pick one (use `docs/adr/`), move the rest, fix internal cross-references, fix `CONTRIBUTING.md` if needed.

**Branch:** `feature/l29-reliability-secrets` from **`develop`** (after L28 merge).

**Target version:** **0.7.3** (patch — no public API breakage).

---

## Goal

Make the assistant **fail loud** instead of silent, get secrets out of source files, and clean up the docs so a security-conscious reviewer doesn't lose trust on first read.

---

## Scope

### §-1 — Merge prep

Branch from latest `develop` (post-L28 merge). Confirm `git status` clean.

### §0 — Cleanup carry-forward

(Cursor will populate from L28 review.)

### §1 — Reflection scheduler failure visibility

In `src/hestia/reflection/scheduler.py` and `runner.py`:

- Add a `FailureLog` ring buffer (size 20) on `ReflectionScheduler` keyed by timestamp + stage (`mining`, `proposal`, `tick`).
- On `except Exception`: append `(datetime.now(UTC), stage, type(e).__name__, str(e)[:200])` to the buffer **before** logging.
- Increment `self.failure_count` (monotonic).
- Expose `ReflectionScheduler.status() -> dict` returning `{"ok": failure_count == 0, "failure_count": int, "last_errors": list[dict], "last_run_at": datetime | None}`.
- New CLI subcommand `hestia reflection status` prints status as a small table.

**Tests:**

- `tests/unit/test_reflection_scheduler_failures.py`:
  - `test_failure_recorded_when_inference_raises` — patch `inference.chat` to raise; tick; assert `failure_count == 1` and ring buffer has one entry with `stage="mining"`.
  - `test_ring_buffer_caps_at_20` — induce 25 failures; assert buffer length == 20 and oldest entries dropped.
  - `test_status_reports_clean_when_no_failures` — fresh scheduler ⇒ `status()["ok"] is True`.
- `tests/integration/test_cli_reflection_status.py`:
  - run `hestia reflection status` after a forced failure ⇒ stdout contains failure type and count.

**Commit:** `feat(reflection): record scheduler failures and surface via hestia reflection status`

### §2 — Style scheduler failure visibility

Same pattern in `src/hestia/style/scheduler.py`. Surface via `hestia style show` (extend the existing command rather than adding a new one). Show a `Failures:` section beneath the profile.

**Tests:** mirror §1 in `tests/unit/test_style_scheduler_failures.py`.

**Commit:** `feat(style): record scheduler failures and surface via hestia style show`

### §3 — Visible warnings on missing personality / calibration

In `src/hestia/cli.py` (or the bootstrap module if L30 has already landed — L29 is **before** L30, so still in `cli.py`):

- After resolving SOUL.md path, if the file does not exist, **emit a `click.echo` warning to stderr** (yellow if TTY) and `logger.warning`. Do **not** crash.
- Same for `docs/calibration.json`.
- Honor environment overrides: `HESTIA_SOUL_PATH`, `HESTIA_CALIBRATION_PATH`. Document in README quickstart.

**Tests:**

- `tests/integration/test_cli_missing_soul_warns.py` — run a CLI subcommand with a non-existent `HESTIA_SOUL_PATH`; capture stderr; assert warning text contains the path.
- `tests/integration/test_cli_env_override_paths.py` — set `HESTIA_SOUL_PATH` to a tmp file; assert it is used.

**Commit:** `feat(cli): warn on missing SOUL.md and calibration; honor env path overrides`

### §4 — Email password env var

In `src/hestia/config.py::EmailConfig`:

- Add `password_env: str | None = None`.
- At read time (`adapter.py::_smtp_connect` / `_imap_connect`, or in `EmailConfig.__post_init__`), prefer `os.environ[self.password_env]` if `password_env` set; fall back to `self.password`. Raise a clear error if both are unset and email is enabled.
- Update `docs/guides/email-setup.md` with the env-var pattern as the **primary** recommended approach.

**Tests:**

- `tests/unit/test_email_config_password_env.py`:
  - `test_password_env_resolves_from_environment` — set `password_env="EMAIL_TEST_PW"` + monkeypatch env; assert resolved value.
  - `test_password_env_missing_raises` — `password_env` set but env var unset ⇒ `EmailConfigError`.
  - `test_plaintext_password_still_works` — backward compat.
  - `test_env_takes_precedence_over_plaintext` — both set ⇒ env wins.

**Commit:** `feat(email): support password_env for credential-from-environment`

### §5 — Web-search provider type narrowing

In `src/hestia/config.py::WebSearchConfig`:

- Change `provider: str` to `provider: Literal["tavily", ""] = ""`.
- Update docstring to reflect the actual support matrix.
- Where the factory raises `ValueError` for unknown providers, narrow the message to mention that only `tavily` is wired.

**Tests:**

- Update existing `tests/unit/test_web_search*` to assert the factory message no longer references `"brave"`.

**Commit:** `fix(web-search): drop unimplemented brave provider from public type`

### §6 — `SECURITY.md` refresh

Rewrite `SECURITY.md` to:

- Supported versions table updated to `0.7.x` (current) supported, everything older unsupported.
- New "Trust profiles" subsection summarising `TrustConfig`, the four default profiles, and the confirmation flow.
- New "Egress audit" subsection — explain that all outbound HTTP requests are logged via `TraceStore` and how to query them (`hestia audit egress` if it exists; check and document the actual command).
- New "Prompt-injection scanner" subsection — explain the annotate-not-block design and how to tune the entropy threshold.
- Replace the disclosure line with a real address (Dylan's preference: GitHub Security Advisory link or a direct email; default to "Open a private GitHub Security Advisory at <repo URL>/security/advisories/new" if the maintainer prefers).

No tests; doc-only commit.

**Commit:** `docs(security): refresh SECURITY.md for 0.7.x trust + audit + scanner`

### §7 — ADR consolidation

- Move `docs/development-process/decisions/ADR-0014-context-resilience.md`, `ADR-0015-llama-server-coexistence.md`, `ADR-0017-prompt-injection-detection-and-egress-audit.md`, `ADR-0018-reflection-loop-architecture.md` → `docs/adr/`.
- Renumber if collisions exist (ADR-0019 already lives in `docs/adr/`). After move, the canonical ordering is ADR-0014, 0015, 0017, 0018, 0019, 0022, 0024. Leave gaps; do **not** renumber existing files.
- `git grep -n "docs/development-process/decisions"` and update every reference in the repo (CONTRIBUTING.md, READMEs, other ADRs cross-linking).
- Add a redirect note at `docs/development-process/decisions/README.md`: `Moved to docs/adr/. See git history.` (or delete the directory if empty after move and references updated).

No tests; structural move.

**Commit:** `docs(adr): consolidate decisions into docs/adr/`

### §8 — Version bump + handoff

- `pyproject.toml` `version = "0.7.3"`.
- `uv lock`.
- `CHANGELOG.md` — `## [0.7.3] — 2026-04-18` summarising every section above.
- `docs/handoffs/L29-reliability-secrets-handoff.md`.

**Commits:**

- `chore(release): bump to 0.7.3`
- `docs(handoff): L29 reliability + secrets report`

---

## Required commands

```bash
uv lock
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/hestia tests
git grep -n "docs/development-process/decisions" -- ':!docs/development-process/kimi-loops/' ':!docs/development-process/kimi-loop-log.md'
```

The last command must return **no matches** outside the kimi-loops/log files (which are historical and immutable).

---

## `.kimi-done` contract

```
HESTIA_KIMI_DONE=1
LOOP=L29
BRANCH=feature/l29-reliability-secrets
COMMIT=<sha>
TESTS=passed=N failed=0 skipped=M
MYPY_FINAL_ERRORS=0
```

---

## Critical Rules Recap

- One commit per section.
- Conventional commits.
- **No** code refactors beyond what's needed for the listed fixes (engine/cli refactors are L30+).
- ADR moves are **literal moves** — do not rewrite ADR bodies.
- Push the feature branch and stop. Cursor merges.
