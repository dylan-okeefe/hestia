# Kimi loop L33 — email connection pool, scanner tuning, skills feature flag, minor cleanups

## Review carry-forward

(Cursor populates after L32 review.)

From **external review (2026-04-18)**:

- `EmailAdapter` opens a fresh `IMAP4_SSL` (TLS handshake + IMAP `LOGIN` + `SELECT`) for **every** operation: `list_messages`, `read_message`, `search_messages`, `create_draft`, `send_draft`, `move_message`, `flag_message`. A single `email_list` + `email_read` round trip is **2 TLS handshakes + 2 logins**. ~300–500ms per call. Many providers rate-limit aggressive reconnects.
- `InjectionScanner.entropy_threshold = 4.2` (`src/hestia/security/injection.py:28`). Real tool outputs (JSON responses, minified CSS, base64 blobs, technical docs) routinely exceed this. The scanner false-positives constantly, and its annotation pollutes model context. Defeats trust in the scanner as a signal.
- The skills framework (`@skill` decorator, `SkillState`, `SkillStore`, CLI commands `hestia skills`, DB table) is **not invoked anywhere** during a turn. README is honest about it being preview, but the public-facing CLI commands and decorator look ready-to-use. A user who writes a skill will be confused when nothing happens. **Gate behind a feature flag** with a clear preview label until L34/post-release work wires it in.
- `_format_datetime` is defined as a closure inside `schedule_show` capturing nothing. Belongs at module scope.
- `DefaultPolicyEngine.should_delegate` matches keywords (`"research"`, `"analyze deeply"`) inline. Surprising trigger paths (`"I'd like to research my family history"` → delegation). Move to a named constant, expose via `PolicyConfig.delegation_keywords` so it's tunable/inspectable.
- `SchedulerConfig` has only one field (`tick_interval_seconds`). Fine for future extensibility — note in a comment, no change.
- `MatrixAdapter._extract_in_reply_to` schema validation is mostly fine (existing `isinstance` checks). Add an explicit unit test for malformed `event.source` to lock the contract.

**Branch:** `feature/l33-perf-and-polish` from **`develop`** (post-L32 merge).

**Target version:** **0.7.7** (patch).

---

## Goal

Take the slowest hot path (email adapter), the noisiest signal (injection scanner), and the most-confusing-to-new-users feature (skills) from "rough" to "shippable to a public repo".

---

## Scope

### §-1 — Merge prep

Branch from `develop` post-L32. Baseline pytest/mypy.

### §0 — Cleanup carry-forward

(Cursor populates from L32 review.)

### §1 — `EmailAdapter` connection pool / context manager

Add an `async`-friendly connection context manager that reuses one IMAP connection within a single tool invocation. Two-step approach:

1. **Per-invocation reuse** (this loop): introduce `async with adapter.imap_session() as conn:` that calls `_imap_connect()` once at entry, `conn.logout()` at exit. Refactor each tool method to use it.
2. **Cross-invocation pool** (deferred to a later loop if needed): document in the new ADR that long-lived pooling is intentionally out of scope here because IDLE/auth-token freshness adds complexity; revisit if profiling shows real cost.

For now, even step 1 cuts list+read from 2 handshakes to 1 when called back-to-back inside the same tool implementation (e.g. `email_search` followed by `email_read` of each result, if any tool composes them). Add a thin wrapper tool `email_search_and_read(query, limit=5)` that demonstrates the pattern and gives users a 1-call shortcut.

**Tests:**

- `tests/unit/test_email_session_reuse.py`:
  - `test_session_uses_single_connection` — patch `IMAP4_SSL` with a counting mock; run two operations inside one `imap_session`; assert constructor called once.
  - `test_session_closes_on_exit` — assert `logout()` called even on exception.
- `tests/integration/test_email_search_and_read.py` — exercise the new composite tool against a mock IMAP server (or the existing email test fixture).

### §2 — Injection scanner tuning

In `src/hestia/security/injection.py`:

- Default `entropy_threshold = 5.5` (raised from 4.2). Document the rationale in the docstring with the empirical baseline ranges (English text ~4.2, JSON ~5.0–5.5, base64 ~6.0).
- Add a `noise_filters` step before the entropy check:
  - If content is parseable as JSON ⇒ skip entropy check (still run regex patterns).
  - If content matches a base64-only regex (≥80% of chars in `[A-Za-z0-9+/=]`, length ≥ 100) ⇒ skip entropy check.
  - If content looks like CSS/HTML (`<` then `>` count ratio test, or contains `{` `}` `;` density typical of CSS) ⇒ skip entropy check.
- These filters do **not** disable the regex pattern check — known prompt-injection phrases are still flagged.
- Expose threshold and filter toggles on `SecurityConfig` (`injection_entropy_threshold: float = 5.5`, `injection_skip_filters_for_structured: bool = True`).

**Tests:**

- `tests/unit/test_injection_scanner_tuning.py`:
  - `test_json_no_longer_false_positives` — minified JSON of length 1KB ⇒ no annotation when `injection_skip_filters_for_structured=True`.
  - `test_base64_blob_skipped` — 1KB base64 ⇒ no annotation.
  - `test_known_pattern_still_flagged_in_json` — JSON containing `"ignore previous instructions"` still flagged.
  - `test_threshold_5_5_default_for_english_text` — random English paragraph ⇒ no annotation.
  - `test_high_entropy_random_bytes_still_flagged` — uniformly random bytes printable ⇒ flagged.

### §3 — Skills framework feature-flag

In `src/hestia/skills/__init__.py` (or wherever the public surface lives):

- Add `def _experimental_enabled() -> bool: return os.environ.get("HESTIA_EXPERIMENTAL_SKILLS") == "1"`.
- `SkillRegistry.register` (and the `@skill` decorator) **raise** `ExperimentalFeatureError` when called without the env var set. The error message tells the user: "Skills are an experimental preview. Set HESTIA_EXPERIMENTAL_SKILLS=1 to opt in. See README.md#skills."
- `hestia skills *` CLI commands check the same flag at command entry; print an informative message and exit nonzero if disabled.
- Update README skills section: rename to "Skills (experimental preview)" with a callout box explaining the flag and that skills are not invoked yet.

**Tests:**

- `tests/unit/test_skills_feature_flag.py`:
  - `test_register_without_flag_raises` (clear env var first).
  - `test_register_with_flag_works` (set env var via monkeypatch).
  - `test_cli_skills_list_disabled_message` — invoke without flag; assert nonzero exit and informative stderr.

### §4 — `_format_datetime` to module scope

Move the `_format_datetime` closure from inside `schedule_show` (in `cli.py` or wherever it lives now post-L30) to a module-level helper in the same file (or `src/hestia/util/datetime.py` if a util module exists). Update callers.

**Tests:** existing schedule tests continue to pass; no new tests required.

### §5 — `should_delegate` keyword constant + config

In `src/hestia/policy/`:

- Define `DEFAULT_DELEGATION_KEYWORDS: tuple[str, ...] = ("research", "analyze deeply", ...)` as a module-level named constant. (Audit the current inline list in `DefaultPolicyEngine.should_delegate` first.)
- Add `PolicyConfig.delegation_keywords: tuple[str, ...] | None = None`. When `None`, fall back to `DEFAULT_DELEGATION_KEYWORDS`.
- `should_delegate` reads from `self._config.delegation_keywords or DEFAULT_DELEGATION_KEYWORDS`.
- Document the surprising trigger ("I'd like to research my family history" delegates) in the docstring and recommend overriding via config for production deployments.

**Tests:**

- `tests/unit/test_policy_delegation_keywords.py`:
  - `test_default_keywords_used` — message containing "research" ⇒ delegation true.
  - `test_custom_keywords_override` — config overrides exclude "research" ⇒ delegation false.
  - `test_empty_tuple_disables_keyword_delegation` — `delegation_keywords=()` ⇒ never delegates by keyword.

### §6 — Matrix `_extract_in_reply_to` malformed-source test

`tests/unit/test_matrix_in_reply_to_parser.py`:

- `test_well_formed_reply` — full nested `m.relates_to.m.in_reply_to.event_id` returns the id.
- `test_missing_relates_to` — returns `None`.
- `test_relates_to_not_dict` — `m.relates_to` is a string ⇒ returns `None` (no exception).
- `test_in_reply_to_not_dict` — same defensive path.
- `test_event_id_not_string` — returns `None`.
- `test_arbitrary_exception_swallowed` — patch `event.source` to raise on access; method returns `None`.

No production code changes required if existing isinstance guards already cover these — Cursor confirmed they do. This loop's job is to **lock** the contract so any future "simplification" of that helper has to delete these tests intentionally.

### §7 — Version bump + handoff

- `pyproject.toml` → `0.7.7`.
- `uv lock`.
- `CHANGELOG.md`.
- `docs/adr/ADR-0022-skills-preview-feature-flag.md`.
- `docs/handoffs/L33-perf-and-polish-handoff.md`.

**Commits:**

- `perf(email): per-invocation IMAP session reuse + email_search_and_read tool`
- `fix(security): tune injection scanner threshold and skip noise for structured content`
- `feat(skills): gate experimental framework behind HESTIA_EXPERIMENTAL_SKILLS flag`
- `refactor(cli): hoist _format_datetime to module scope`
- `feat(policy): expose delegation_keywords on PolicyConfig`
- `test(matrix): lock _extract_in_reply_to schema validation`
- `docs(adr): ADR-0022 skills preview feature flag`
- `chore(release): bump to 0.7.7`
- `docs(handoff): L33 perf + polish report`

---

## Required commands

```bash
uv lock
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/hestia tests
```

---

## `.kimi-done` contract

```
HESTIA_KIMI_DONE=1
LOOP=L33
BRANCH=feature/l33-perf-and-polish
COMMIT=<sha>
TESTS=passed=N failed=0 skipped=M
MYPY_FINAL_ERRORS=0
```

---

## Critical Rules Recap

- Skills feature-flag MUST raise (not silently no-op) when the env var is missing — visibility matters more than convenience.
- Scanner threshold change is a behavior shift; document it in CHANGELOG explicitly.
- One commit per section.
- Push and stop.
