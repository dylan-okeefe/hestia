# Hestia Post-Cleanup Re-Evaluation — develop branch, April 26, 2026

Re-evaluation after L60–L74 merged. Compares current state against the pre-cleanup evaluation and cross-reference analysis.

**Codebase:** 18,065 lines across 121 Python files. 26,187 lines of tests across 142 files.

---

## What Got Fixed

The cleanup arc addressed the majority of the issues from all three evaluations. Here's a concrete accounting.

### Fully resolved

**InferenceClient (L64):** The 7 copy-pasted try/except blocks are gone. `_request()` helper handles all HTTP error translation in one place. `__aenter__`/`__aexit__` exist. `app.close()` is called in both the CLI chat loop and the platform runner shutdown path. This is clean.

**SlotManager (L65):** `_pick_lru_victim` now calls `get_sessions_batch` — one query instead of N. `_evict_session_locked` releases the lock before HTTP I/O (slot_save/slot_erase) and re-acquires it after. A concurrency stress test file exists at `tests/integration/test_slot_manager_concurrency.py` (124 lines). The slot-save failure now raises `InferenceServerError` instead of silently continuing.

**Meta-tool dispatch (L66):** The open-coded `if tc.name == "list_tools"` type switch is replaced with `self._meta_tools` dict. Adding a meta-tool is one dict entry plus a handler method. `message_to_dict` moved to `core/serialization.py` — both `inference.py` and `builder.py` import from the canonical location, no circular import.

**Bounded caches (L67):** `_tokenize_cache` is now an `OrderedDict` capped at 4096 entries with LRU eviction. `_last_edit_times` has a `_prune_last_edit_times()` method that evicts stale entries on each access. `_join_overhead` appears to be computed once. Static system prompt token counts are cached via `_system_token_count`/`_last_system_content`.

**list_dir (L67 extension):** Fixed. The entire directory iteration runs inside a single `asyncio.to_thread(_build_listing)` call. Only the initial `target.is_dir` guard is a separate dispatch, which is fine.

**Memory store (L68):** `_resolve_scope` extracted and used everywhere, with a partial-identity leak guard. `hasattr` dead code removed. Tag matching uses pipe-delimited exact patterns (`tag|%`, `%|tag|%`, `%|tag`) — down from 6 LIKE clauses to 3. `_sanitize_fts5_query` now handles `*`, `^`, hyphens, and colons by wrapping in double quotes.

**Exception handling (L69):** Unacknowledged `except Exception` is down from 40 to 32. Of the remaining 32, many are in defensible boundary positions (telegram adapter voice handling, email tools, doctor checks, config validation). The 24 acknowledged (`noqa: BLE001`) catches are reasonable.

**App context (L71):** `CoreAppContext`, `FeatureAppContext`, and `CliAppContext` collapsed into single `AppContext` class. `make_app()` is now ~55 lines, delegating to `_load_and_validate_config`, `_warn_on_missing_files`, `_register_optional_features`. Backward-compatible aliases exist (`CliAppContext = AppContext`). The class uses `@functools.cached_property` for lazy subsystems (inference, context_builder, slot_manager, handoff_summarizer, reflection_scheduler, style_scheduler). `app.py` went from 627 lines to 502.

**SSRF / tool boundaries (L72):** `curl_cffi` fallback is now opt-in via `config.use_curl_cffi_fallback`. Tool calls per turn are capped at `max_tool_calls_per_turn` (default 10) in `PolicyConfig`. Excess calls get error results, not silent truncation.

**Security defaults (L63):** `allowed_roots` defaults to `[]` (deny-all). `EmailConfig.__repr__` masks password. `TelegramConfig.__repr__` masks `bot_token`. `TrustConfig.developer()` emits `logger.warning()`. `hestia doctor` fails on `developer` preset outside dev environment.

**Startup validation (L74):** `_validate_config_at_startup` checks telegram token consistency, email host completeness, and database directory existence.

**User-facing errors (L74):** `sanitize_user_error` in finalization now maps specific error types to human-friendly messages (InferenceTimeoutError → "taking longer than expected", ContextTooLargeError → "conversation has grown very long", ToolExecutionError → names the tool).

**Concurrent tool safety (L70 repurposed):** `_run_one` in `_execute_tool_calls` wraps each concurrent dispatch in try/except so one failing tool doesn't cancel siblings.

**Partial identity scope (L70 repurposed):** `_resolve_scope` guards against one of platform/platform_user being None.

### Partially resolved

**Orchestrator engine thinning (L62):** The decomposition into TurnAssembly/TurnExecution/TurnFinalization is complete and the phase classes are substantial. But `engine.py` is still 308 lines with 15 methods, 5 of which are one-line delegates (`_prepare_turn_context`, `_run_inference_loop`, `_handle_context_too_large`, `_handle_unexpected_error`, `_finalize_turn`). These could be inlined into `process_turn` to make the engine a ~150-line coordinator. Minor — the structure is correct even if the cost hasn't been fully paid down.

**Exception handling (L69):** 32 unacknowledged catches remain. 8 are in the Telegram adapter (voice processing pipeline — legitimately tricky), 7 in email_tools (each tool method wraps its IMAP/SMTP work), 4 in doctor.py (health checks are inherently catch-all), 2 in config.py (croniter validation). These are mostly defensible but several in email_tools could be narrowed to `(OSError, imaplib.IMAP4.error, smtplib.SMTPException)`. The Telegram voice ones are the hardest to narrow because they involve Whisper/Piper subprocess calls.

**Feature subsystem audit (L73):** Skills was fully removed — the `src/hestia/skills/` directory is gone, no dangling imports remain. This is the right call; the scaffolding had no working meta-tool and was dead weight. Reflection is at 752 lines (target was ≤350). Style is at 899 lines (target was ≤350). Neither subsystem was slimmed, but both are behind `enabled: False` flags and work correctly when enabled.

---

## What's Still Open

These are items that appeared in the evaluations and/or the cross-reference analysis but remain unaddressed.

### Bugs / correctness

1. **`_italic_repl` dead code still present.** Lines 67–72 of `telegram_adapter.py` still contain the `if "*" in inner or "<b>" in inner or "</b>" in inner` check that can never trigger. L70 was repurposed for memory scope/concurrent tool safety and the Telegram markdown cleanup was dropped.

2. **`test_builtin_tools_new.py` duplicate still exists.** Both `test_builtin_tools.py` and `test_builtin_tools_new.py` are present in `tests/unit/`. This was supposed to be consolidated in L70 §3.

3. **`CliAppContext` alias still used as a type annotation.** `cli.py` line 16 imports `CliAppContext` and uses it as the type for the click pass_obj. `commands/history.py` also uses `CliAppContext`. These should be `AppContext` — the aliases exist only for backward compat and shouldn't be the canonical annotation in first-party code.

### Security

4. **`egress_events` still stores full URLs with potential credentials.** `_record_egress(url, status, size)` in `http_get.py` passes the full URL including query parameters. No stripping or redaction. If the model fetches `https://api.example.com/data?api_key=SECRET`, the key is persisted in cleartext.

### Architecture / structure

5. **`cli.py` is still 719 lines of registration boilerplate.** 59 command/group decorators. Every command follows the same thin-wrapper pattern delegating to `commands/`. Not touched by any loop.

6. **Reflection at 752 lines, Style at 899 lines.** L73 targeted ≤350 lines each. The subsystems were not slimmed. Both are behind `enabled: False` flags and work correctly, so this is a contributor-experience issue, not a user-facing one. Reflection+style combined (1,651 lines) is comparable to the orchestrator (1,430 lines).

7. **Engine one-line delegates.** Minor, but `engine.py` would be cleaner at ~150 lines if `_prepare_turn_context`, `_run_inference_loop`, `_handle_context_too_large`, `_handle_unexpected_error`, and `_finalize_turn` were inlined into `process_turn`.

### Efficiency

9. **Token counting still one HTTP round-trip per message.** The static-content caching is a good step, but history messages are still individually counted. A turn with 50 history messages is 50 POST /tokenize requests. Batching these (if llama.cpp supports it) would be a meaningful latency improvement.

### Missing from cross-reference recommendations

10. **Email adapter connection lifecycle** was recommended for L64 but not addressed. IMAP/SMTP connections in `email/adapter.py` (568 lines) still have fragile lifecycle management with multiple try/except blocks that can leave connections in unclear states.

11. **Per-user/session rate limiting** was recommended for L72 but not addressed. A user can still fire unlimited turns per minute.

---

## What Improved Most

The biggest wins from this cleanup arc, ranked by impact:

1. **InferenceClient lifecycle.** From "7 copy-pasted blocks, no close(), no context manager" to a clean, single-responsibility HTTP wrapper with proper lifecycle. This was the most impactful code-quality improvement.

2. **App context collapse.** From a 627-line three-class hierarchy with 25 forwarding properties to a 502-line single class with `cached_property`. Adding a new subsystem is now one change, not four.

3. **SlotManager correctness.** Batch query, lock release before I/O, and loud failure on save errors. This is daemon-grade code now where it was previously "works on my laptop" quality.

4. **Security defaults.** `allowed_roots=[]`, bot_token/password redaction, developer preset guardrails. A new user who skips reading SECURITY.md is now safe by default.

5. **Meta-tool dispatch table.** From an open-coded type switch to a one-line-to-add pattern. The extensibility improvement is genuine.

6. **Bounded caches.** Three unbounded growth sources (tokenize cache, edit times, join overhead) are now bounded or permanently cached. Daemon stability under long uptime is qualitatively improved.

---

## Honest Assessment

The L60–L74 arc was ambitious (15 loops) and delivered solidly on the core issues — roughly 75% of the identified problems are genuinely fixed. Skills was correctly removed entirely. The areas where it fell short are:

- **L70 was repurposed** for memory scope and concurrent tool safety (both good fixes), but the Telegram markdown cleanup was dropped. The dead code and duplicate test file remain.
- **L73 (feature subsystem audit) was partial.** Skills removed (good), but Reflection and Style weren't slimmed.
- **Several cross-reference additions** (egress URL redaction, email lifecycle, cli.py boilerplate, per-session rate limiting) were recommended but not picked up.

The codebase is materially better than before the arc. The core loop (orchestrator → inference → tools → response) is now clean, well-factored, and has proper lifecycle management. The remaining issues are concentrated in the periphery — optional feature subsystems, CLI registration boilerplate, and a few security niceties that aren't blocking but should be addressed.

### If I were prioritizing a next arc:

1. **Finish the Telegram cleanup.** Remove `_italic_repl` dead code, consolidate the duplicate test file. A 10-minute fix that was promised and dropped.
2. **Strip credentials from egress URLs.** Security hygiene that should have been in L72.
3. **Slim Reflection and Style.** L73's original targets (≤350 lines each) were right. Both work but carry disproportionate weight for opt-in features.
4. **Inline engine.py delegates.** Pay down the remaining decomposition debt and get the engine to ~150 lines.
5. **Narrow email_tools exception handling.** The 7 broad catches in email_tools.py could be `(OSError, imaplib.IMAP4.error, smtplib.SMTPException)` without losing safety.
6. **Acknowledge remaining broad catches.** Add `# noqa: BLE001` with brief comments to the ~32 remaining unacknowledged `except Exception` catches that are genuinely intentional.

---

## Release Readiness Assessment (v0.11.0)

### Verdict: ready to ship

The core is solid. The chat loop, tool dispatch, memory, scheduler, context budgeting, KV-cache slot management, trust/policy system, and multi-platform adapters all work and are well-factored. The security posture is good. The quickstart path (clone → `uv sync` → `hestia init` → `hestia chat`) works. CI runs lint, typecheck, and tests on Python 3.11/3.12. The repo has LICENSE, SECURITY.md, CONTRIBUTING.md, CHANGELOG, deploy scripts, systemd templates, and a README with a working quickstart. These are the table-stakes for a credible public release.

### Pre-release checklist

**Must-fix (tag blockers):**

- [ ] Remove `_italic_repl` dead code in `telegram_adapter.py` lines 70–71 (the `if "*" in inner or "<b>" in inner` branch that can never trigger). Three-line delete.
- [ ] Consolidate `tests/unit/test_builtin_tools.py` and `tests/unit/test_builtin_tools_new.py`. Merge or delete whichever is stale. Two test files with similar names signals an unfinished refactor.
- [ ] Replace `CliAppContext` type annotation with `AppContext` in `cli.py` (line 16 import, line 554/631 annotations) and `commands/history.py` (lines 11, 14, 51). The aliases exist for backward compat but first-party code should use the canonical name.
- [ ] Update CHANGELOG with an `[Unreleased]` or `[0.11.0]` section covering the L60–L74 arc. Key items: security hardening (deny-all defaults, credential redaction, developer preset guardrails), InferenceClient consolidation, app context collapse to single class, SlotManager correctness fixes, bounded caches, tool-call-per-turn cap, skills subsystem removed, startup config validation, `hestia history` command, user-facing error messages improved.
- [ ] Bump version in `pyproject.toml` from `0.10.0` to `0.11.0`.

**Should-fix (do if time permits, not blockers):**

- [ ] Strip query parameters from URLs in `_record_egress()` before persisting to `egress_events`. Prevents accidental credential storage in the audit log.
- [ ] Add `# noqa: BLE001` with brief justification comments to the ~32 remaining unacknowledged `except Exception` catches. Makes the codebase look intentional rather than hurried when someone runs `ruff check --select BLE001`.
- [ ] Consider moving `docs/development-process/` (105 internal files — loop specs, handoffs, reviews) to `docs/internal/` or noting in `docs/README.md` that it's development archaeology. The user-facing docs (10 guides, 33 ADRs, deploy scripts) stand well on their own and shouldn't be buried under process files.

**Post-release (next arc):**

- [ ] Slim Reflection (~752 lines) and Style (~899 lines) toward their original L73 targets of ≤350 each.
- [ ] Inline engine.py one-line delegates.
- [ ] Narrow email_tools exception handling.
- [ ] Address email adapter connection lifecycle.
- [ ] Consider per-session rate limiting.

### Release process

```bash
# 1. Fix the must-fix items above on develop
# 2. Final check
uv run ruff check src/
uv run mypy src/hestia
uv run pytest tests/unit/ tests/integration/ -q

# 3. Merge develop to main
git checkout main
git merge develop

# 4. Tag
git tag -a v0.11.0 -m "v0.11.0: security hardening, structural cleanup, skills removal"
git push origin main --tags

# 5. Create GitHub release
#    Use the CHANGELOG entry as release notes.
#    Mark as pre-release if desired (signals "stable but still evolving").
```
