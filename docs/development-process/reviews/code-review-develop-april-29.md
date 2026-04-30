# Code Review — develop branch, April 29, 2026

Full code review of the Hestia codebase on the develop branch as it stands post-L60–L74, post-checklist fixes (duplicate test file consolidated, `CliAppContext` annotations replaced, `except Exception` catches acknowledged, CHANGELOG updated, version bumped to 0.11.0, egress URL query stripping added). This is a fresh review, not a diff against the post-cleanup evaluation.

Incorporates and reconciles two audits: the kimi code review from April 22 (`kimi-code-review-2026-04-22.md`, M1–M3, L1–L3) and a fresh copilot evaluation (pasted, April 2026) against current code state. Also addresses streaming-to-Telegram status.

Reviewer context: advisory only — no changes made.

---

## Copilot Evaluation — Pre-Release Checklist Confirmations

The copilot's fresh evaluation confirmed every item on the pre-release checklist is resolved:

- ✅ `_italic_repl` — the `"*" in inner` clause was removed; the remaining `<b>` guard is NOT dead code (see dedicated section below).
- ✅ `test_builtin_tools_new.py` — consolidated; doesn't exist.
- ✅ `CliAppContext` annotations — `cli.py` uses `AppContext` throughout; alias in `app.py` is backward-compat-only.
- ✅ CHANGELOG — complete `[0.11.0]` section.
- ✅ Version — `pyproject.toml` at `0.11.0`.
- ✅ Egress URL stripping — `_record_egress` strips query params and fragments before persisting.
- ✅ All `except Exception` catches acknowledged — 53 total, 0 unacknowledged. Every one has `# noqa: BLE001` with contextual comment.
- ✅ Reflection/Style sizes — reflection is ~380 lines across all files, style is ~329 lines. Both well under the 350-line target the previous analysis worried about.
- ✅ Engine one-line delegates — inlined into `process_turn`. The engine is now a clean coordinator.
- ✅ Per-session rate limiting — `SessionRateLimiter` with token-bucket semantics, wired through `AppContext` and `RateLimitConfig`. Default-disabled but complete.

---

## Kimi Code Review Reconciliation (April 22 — M1–M3, L1–L3)

The earlier kimi code review identified 3 medium-severity and 3 low-severity issues. Here's their current status:

### Resolved by L60–L74

**M1 — Memory.save orphan rows when called outside identity context:** Fixed. `_resolve_scope` (added in L68) fills in missing platform/platform_user from runtime ContextVars. If both remain None after the lookup, `save()` now emits `logger.warning("memory.save called outside an identity context; saving as unscoped")`. The silent ghost-row problem is gone.

**M2 — Memory.search partial-scope isolation leak:** Fixed. `_resolve_scope` (lines 224–232 of `store.py`) detects when exactly one of platform/platform_user is set and normalizes to `(None, None)` with a warning: `"Partial identity context ... treating as unscoped to avoid isolation leak"`. The fail-closed behavior the audit recommended is implemented. All memory operations (`save`, `search`, `list_all`, `delete`, `count`) route through `_resolve_scope`.

**M3 — `_execute_tool_calls` exception propagation from `asyncio.gather`:** Fixed. `_run_one` in `execution.py` (lines 249–258) now wraps the entire `_dispatch_tool_call` in a try/except that catches `Exception` and returns `ToolCallResult.error(...)`. This is the "wrap `_run_one`'s body" fix the audit recommended. The gather no longer explodes on a single tool failure.

### Still open

**L1 — `session.platform == "scheduler"` literal in `default.py` line 258:** Still present. No `PLATFORM_SCHEDULER` constant was extracted. The literal is defensive (no code currently creates sessions with `platform="scheduler"` — the scheduler uses `scheduler_tick_active` ContextVar instead), but the commit message from M-12 overstated what shipped. Low priority — cosmetic.

**L2 — Session-collision retries log at DEBUG:** Not verified whether this changed. The TOCTOU fix in `get_or_create_session` was rewritten with INSERT ON CONFLICT DO NOTHING (see the session store code), so the retry-and-re-select path is different now. The collision case is now handled at the database level rather than application-level retry, making the logging concern mostly moot.

**L3 — Single lock for STT and TTS init in VoicePipeline:** Not addressed. Still a single `_init_lock` for both models. Impact is "TTS starts late once, ever" during the first voice message if STT is loading concurrently. Negligible.

---

## Streaming to Telegram — Status

**Hestia does not stream responses to Telegram.** The `InferenceClient.chat()` method (lines 144–237 of `core/inference.py`) sends a single POST to `/v1/chat/completions` and waits for the complete response. There is no SSE streaming, no chunked transfer, no progressive delivery.

The Telegram adapter has `edit_message` with rate limiting (1.5s between edits) and the `_md_to_tg_html` conversion, which are the infrastructure you'd need for progressive display. But the orchestrator's `respond_callback` is called once with the final complete response (`await ctx.respond_callback(content)` in `execution.py` line 181). There is no intermediate callback during generation.

**What streaming would require:**

1. `InferenceClient` needs a `chat_stream()` method that opens an SSE connection to `/v1/chat/completions` with `"stream": true` and yields content deltas.
2. The orchestrator execution loop needs to handle streaming responses differently — accumulate content while yielding partial results through a streaming callback.
3. The `ResponseCallback` type (currently `Callable[[str], Awaitable[None]]`) would need a streaming variant or a separate `StreamCallback` that receives deltas.
4. The Telegram adapter would use `send_message` for the first chunk, then `edit_message` (rate-limited) to update the message as more content arrives.

This is a meaningful architectural change — it touches inference, orchestrator, platform adapters, and the callback contract. It's a post-v0.11.0 feature, not a blocker. The infrastructure (edit_message rate limiting, HTML conversion) is already in place for the Telegram side; the gap is entirely in the inference and orchestrator layers.

**Kimi instruction note:** If this becomes a loop, frame it as: "Add streaming inference support. The InferenceClient needs a `chat_stream` method using httpx SSE. The orchestrator execution loop needs to yield partial content through a new streaming callback. The Telegram adapter already has rate-limited `edit_message` — wire the streaming callback to call `send_message` on first chunk, then `edit_message` on subsequent chunks with the existing rate limiter. Do NOT change the non-streaming path — both must coexist, with streaming gated behind a config flag."

---

## Critical: `AppContext.close()` never closes the inference client

**File:** `src/hestia/app.py`, line 258

```python
async def close(self) -> None:
    """Close lazily-created resources."""
    if hasattr(self, '_inference') and self._inference is not None:
        await self._inference.close()
```

The cached property is named `inference` (no underscore prefix), but `close()` checks for `_inference`. Since `functools.cached_property` stores its value in `instance.__dict__['inference']`, the attribute `_inference` never exists, so `hasattr(self, '_inference')` is always `False`. The inference client's `httpx.AsyncClient` is never closed by `app.close()`.

**Impact:** In CLI mode (`commands/chat.py` lines 88, 122), the httpx client leaks. In daemon mode (`platforms/runners.py` line 191) and admin commands (`commands/admin.py` lines 150, 207), the code works around this by calling `app.inference.close()` directly. The scheduler path (`commands/scheduler.py` line 280) calls `app.close()` and therefore also leaks.

**Fix:**

```python
async def close(self) -> None:
    if 'inference' in self.__dict__:
        await self.inference.close()
    if self.email_adapter is not None:
        self.email_adapter.close()
```

Checking `self.__dict__` avoids triggering the `cached_property` descriptor (which would create an InferenceClient just to close it). This is the correct pattern for cleaning up `functools.cached_property` instances.

**Severity:** Bug — resource leak in CLI and scheduler modes. Should be fixed before tagging.

---

## `_italic_repl` is NOT dead code — post-cleanup evaluation was wrong

**File:** `src/hestia/platforms/telegram_adapter.py`, lines 67–74

The post-cleanup evaluation called this dead code. It isn't. The markdown-to-HTML conversion runs in this order: (1) escape HTML, (2) code blocks, (3) inline code, (4) bold `**text**` → `<b>text</b>`, (5) italic `*text*` via `_italic_repl`. After step 4, input like `*text **bold** more*` becomes `*text <b>bold</b> more*`. The italic regex `\*([^*\n]+)\*` then matches the outer asterisks with `inner = "text <b>bold</b> more"`, which contains `<b>`. The guard correctly prevents wrapping already-converted bold content in italic tags, which would produce `<i>text <b>bold</b> more</i>` — valid but semantically wrong (the italic would encompass the bold).

**Action:** Remove from the pre-release checklist. The function is correct and the guard is reachable.

---

## `ToolExecutionError` missing from `classify_error` mapping

**File:** `src/hestia/errors.py`, lines 165–180

The `classify_error` function maps exception types to `(FailureClass, severity)` tuples for failure analytics. The mapping includes `ContextTooLargeError`, `EmptyResponseError`, `InferenceTimeoutError`, `InferenceServerError`, `PersistenceError`, `IllegalTransitionError`, `MaxIterationsError`, and `WebSearchError`. But `ToolExecutionError` is absent. When a tool fails, the failure bundle records `failure_class="unknown"` and `severity="medium"` instead of `failure_class="tool_error"`.

**Impact:** Failure analytics misclassify tool failures. If you ever query failure bundles by class to understand what's going wrong, tool errors are invisible in the `TOOL_ERROR` bucket and inflating `UNKNOWN`.

**Fix:** Add one line to the mapping:

```python
ToolExecutionError: (FailureClass.TOOL_ERROR, "medium"),
```

**Severity:** Bug — analytics misclassification. One-line fix. (Also flagged by the copilot audit as a priority item.)

**Kimi instruction note:** This is a one-line fix in `errors.py`. Add `ToolExecutionError` to the `mapping` dict in `classify_error`. Import is already at the top of the file. Add a test in whatever test file covers `classify_error` that asserts `classify_error(ToolExecutionError("test_tool", ValueError("boom"))) == (FailureClass.TOOL_ERROR, "medium")`.

---

## `SessionRateLimiter` has unbounded bucket growth

**File:** `src/hestia/core/rate_limiter.py`, line 33

```python
self._buckets: dict[str, TokenBucket] = {}
```

`SessionRateLimiter._buckets` grows without bound. Every unique `session_id` gets a `TokenBucket` entry that is never evicted. For a daemon running for weeks with ephemeral sessions (scheduler ticks, one-off Telegram conversations), this is a slow memory leak. It won't matter for personal use but it's the kind of thing a contributor would flag.

**Fix:** Add a max-size eviction (LRU on last-consumed, or a periodic sweep). Or, since the rate limiter is gated behind `config.rate_limit.enabled` (default `False`), note this limitation in a comment and defer.

**Severity:** Minor — daemon memory hygiene. Not a blocker.

---

## `doctor.py` has duplicate `# noqa` comments

**File:** `src/hestia/doctor.py`, lines 62, 235, 439

These lines have the pattern:

```python
except Exception as exc:  # noqa: BLE001 — defensive check boundary  # noqa: BLE001
```

Two `# noqa: BLE001` on the same line. Functionally harmless (ruff only reads the first), but it looks like an automated find-and-replace ran twice. Trivial cleanup.

---

## `_evict_session_locked` lock release/re-acquire is fragile

**File:** `src/hestia/inference/slot_manager.py`, lines 217–231

The eviction method releases `self._lock` before HTTP I/O and re-acquires it after. The comment at line 229 says "asyncio.Lock is reentrant-safe for the same task" — but asyncio.Lock is NOT reentrant. If the except block acquires the lock (line 224) and then the finally block also tries to acquire it (via `if not self._lock.locked()`), the finally branch is skipped because `locked()` returns `True`. This happens to work today, but the reasoning in the comment is wrong.

The real invariant is: on normal exit, the lock is re-acquired in finally; on exception exit, it's re-acquired in except and the finally skips because `locked()` is True. This is correct but relies on `locked()` being a proxy for "this task holds it," which is only true because no other code path can interleave between except and finally in a single-task context.

**Suggestion:** The lock management would be clearer with an `asyncio.Condition` or by restructuring to always release/reacquire in one place. But the current code is correct for the single-task guarantee provided by asyncio.Lock. A comment correction (remove "reentrant-safe" claim) would be sufficient.

**Severity:** Misleading comment, not a bug.

---

## `ConfirmCallback` is defined in two places

**File:** `src/hestia/orchestrator/engine.py`, line 46; `src/hestia/orchestrator/execution.py`, line 31

Both files define `ConfirmCallback = Callable[[str, dict[str, Any]], Awaitable[bool]]`. The engine version is the one imported by `app.py`. The execution version is used internally. They're identical, but if one changes and the other doesn't, you get a subtle type mismatch. Should be defined once and imported.

**Severity:** Minor — code organization.

---

## `TurnExecution._execute_tool_calls` doesn't wrap serial tools in try/except

**File:** `src/hestia/orchestrator/execution.py`, lines 267–269

Concurrent tools are wrapped in a per-tool try/except (line 253). Serial tools are not:

```python
for idx in serial_indices:
    tc = tool_calls[idx]
    result = await self._dispatch_tool_call(session, tc, allowed_tools)
```

If `_dispatch_tool_call` raises for a serial tool, the exception propagates up and kills the turn. For concurrent tools, exceptions are caught and returned as error results. The asymmetry means a serial tool failure is handled differently (turn-level failure) than a concurrent tool failure (graceful per-tool error). This is arguably intentional — serial tools include confirmation-gated tools where you want the turn to stop if something goes wrong — but it's not documented.

**Suggestion:** Add a comment explaining the intentional asymmetry, or wrap serial tools with the same shield.

**Severity:** Design decision worth documenting.

---

## `for_trust` equality check is fragile

**File:** `src/hestia/config.py`, line 466

```python
enable = trust not in (TrustConfig.paranoid(), TrustConfig())
```

This compares the provided `TrustConfig` instance against freshly-constructed instances using dataclass `__eq__`. This works today because all fields are simple types (strings, bools, lists of strings), but if `TrustConfig` ever gains a field with identity-based equality (e.g., a callback), this breaks silently. Also, `TrustConfig()` and `TrustConfig.paranoid()` are identical, so the tuple has a redundant entry.

**Severity:** Minor.

---

## `_strip_historical_reasoning` creates full message copies every call

**File:** `src/hestia/core/inference.py`, lines 13–31

Every call to `chat()` and `count_request()` creates a new `Message` object for every message in history. For a 50-message history, that's 50 object allocations per inference call (and there may be multiple per turn). Since `Message` is a dataclass, the copy is cheap, but a `dataclasses.replace(msg, reasoning_content=None)` or a conditional (only copy messages that actually have reasoning_content) would be cleaner and marginally faster.

**Severity:** Negligible — micro-optimization.

---

## `_compute_join_overhead` makes 2 tokenization HTTP calls

**File:** `src/hestia/context/builder.py`, lines 179–217

On the first turn of the ContextBuilder's lifetime, this method makes two POST /tokenize calls to measure the per-message join overhead. The result is cached for the life of the builder instance, so this is a one-time cost. But it happens during the first user turn, adding ~200ms of latency to the first response. Moving this to an explicit warm-up step (or computing it from the calibration file) would improve first-turn UX.

**Severity:** UX nit — first-turn latency.

---

## STARTTLS response code check is correct but underdocumented

**File:** `src/hestia/email/adapter.py`, line 140

```python
code, _ = smtp.starttls()
if code != 220:
```

The code check is correct per RFC 3207 (220 = "ready to start TLS"). But `smtplib.SMTP.starttls()` can also raise `smtplib.SMTPException` before returning a code if the server sends a non-STARTTLS response. The `_smtp_connect` method has no except clause of its own — the exception propagates to the caller's `_smtp_session` context manager, which catches it. So it's not a security hole, but the reasoning isn't obvious.

**Fix:** Add a comment above the `starttls()` call noting that `SMTPException` from the call itself is caught by the calling context manager, so the `if code != 220` branch only fires on a "successful but wrong code" response.

**Severity:** Documentation gap — not a bug.

---

## `_record_egress` silences failures at `logger.debug`

**File:** `src/hestia/tools/builtin/http_get.py`, lines 259–261

```python
except Exception:  # noqa: BLE001
    logger.debug("Failed to record egress event", exc_info=True)
```

The catch-all is correct for best-effort audit logging — you don't want a trace-store failure to crash a tool call. But if the database is locked or full, every egress record silently vanishes at DEBUG level, which is invisible under normal logging configuration. If this keeps happening, the operator has no signal.

**Fix:** Promote to `logger.warning` on repeated failures, or at minimum use `logger.info`. A counter pattern (warn once per N failures) would be ideal but not worth the complexity for v0.11.0.

**Severity:** Observability gap — not a bug.

---

## Email adapter's IMAP session uses synchronous `imaplib`

**File:** `src/hestia/email/adapter.py`

The entire email adapter wraps synchronous `imaplib` and `smtplib` calls. While `asyncio.to_thread` is used in the email tools, the `imap_session` context manager at line 62 calls `conn.select(folder)` (line 78), `conn.close()` (line 86), and `conn.logout()` (line 91) without threading — these are synchronous blocking calls on the event loop. In practice this is fine for IMAP (fast operations on an established connection), but it's worth noting for future contributors that the adapter isn't fully async-safe.

**Severity:** Technical debt — not blocking.

---

## Positive observations

To be clear about where the code is strong:

**The orchestrator decomposition is clean.** `engine.py` (278 lines) delegates to `assembly.py` (123 lines), `execution.py` (475 lines), and `finalization.py` (349 lines). The `TurnContext` dataclass replaces what would have been a 20-parameter function signature. State machine transitions are explicit and validated. This is well-factored code.

**The meta-tool pattern is genuinely clever.** Three tool schemas in context instead of 19+, with the dispatch table making extension trivial. The token savings (~2,900/turn) are real and measured. The `_scan_tool_result` injection check on the inner tool result is correct — it checks the actual output, not just the meta-tool wrapper.

**InferenceClient is now clean.** Single `_request()` helper, proper context manager, explicit error types. The tool_call argument validation (lines 207–217 of `inference.py`) catches malformed JSON and non-dict arguments with clear error messages. The empty-choices guard (line 194) handles a real llama-server edge case.

**The session TOCTOU fix is properly database-backed.** `get_or_create_session` uses INSERT ON CONFLICT DO NOTHING with a partial unique index, not application-level locking. The dialect dispatch for SQLite vs PostgreSQL is handled in one method. This is correct.

**The security posture is appropriate for the project's maturity.** `allowed_roots=[]`, SSRF protection with IP-range blocking at the transport layer, credential masking in `__repr__`, developer-preset guardrails, injection scanning on tool results, egress audit with query parameter stripping. These are table-stakes for a framework that runs tools on the user's machine, and they're all done right.

**The error hierarchy is well-designed.** `HestiaError` base class, specific subclasses for each failure mode, `classify_error()` for analytics, `sanitize_user_error()` for end-user messages. The separation between "internal detail" and "user-facing message" is clean throughout.

**Context budgeting is precise.** Real tokenization via POST /tokenize, calibration correction factors from measured data, bounded token cache with LRU eviction, static system prompt caching. This is the kind of engineering that matters when you're constrained to 8K context.

**MemoryStore with FTS5 fallback.** The probe-once pattern for FTS5 support detection is elegant. The tag matching with 3 pipe-delimited LIKE patterns (vs the previous 6) is the right trade-off. `_sanitize_fts5_query` is short, well-documented, and handles the real FTS5 footguns (hyphens, colons, asterisks, carets). The early-return for already-quoted or already-using-operators queries is smart.

**`classify_error` pattern** (minus the `ToolExecutionError` gap). Having a single function that maps exceptions to `(FailureClass, severity)` tuples is a pattern that pays off in failure analytics. Clean, extensible, easy to test.

**`AppContext` with `cached_property`.** The lazy subsystem model is correct and the composition is readable. Adding a new subsystem is one property definition. (The `close()` bug is a consequence of the pattern, not a flaw in the pattern itself.)

---

## Additional findings from copilot audit validation

These items were surfaced by the copilot audit (April 22) and remain relevant:

### `import re` deferred inside `_md_to_tg_html` (telegram_adapter.py line 41)

The `import re` lives inside the function body. Python caches module imports, so this isn't a performance issue, but every other `re` usage in the codebase imports at module level. Move it to the top of the file.

**Kimi instruction note:** Trivial — move `import re` from inside `_md_to_tg_html` to the module-level imports at the top of `telegram_adapter.py`. The function is at line 36; the import should join the other stdlib imports around lines 1–10.

### `_count_body` cache key collision risk (context/builder.py line 359)

The cache key is `"|".join(f"{m.role}:{m.content}" for m in messages)`. If a message's content contains a literal `|system:` string (e.g., a tool result quoting a system prompt), two different message lists could produce the same key. The system-prompt-only fast path (`if len(messages) == 1`) avoids this for the hot path, but the general case is technically vulnerable.

**Severity:** Extremely unlikely in practice. A hash-based key (e.g., `hash(tuple((m.role, m.content) for m in messages))`) would be correct but the current code is fine for v0.11.0.

### `ReflectionRunner._on_failure` typed as `Any | None` (reflection/runner.py)

The failure callback should be `Callable[[str, Exception], None] | None` instead of `Any | None`. The `Any` defeats the type checker at call sites.

**Kimi instruction note:** Change the type annotation on `on_failure` in `ReflectionRunner.__init__` to `Callable[[str, Exception], None] | None`. Import `Callable` from `collections.abc` if not already imported.

### `style/builder.py` — dense formatting, raw SQL needs readability pass

At 99 lines it's compact, but every method runs together with no blank lines, and every SQL query is a single-line string with `# noqa: E501`. The queries are non-trivial JOINs against production tables. This is the one file where readability matters most for correctness review.

**Kimi instruction note:** Reformat `style/builder.py`: add blank lines between methods, break SQL queries into multi-line triple-quoted strings with alignment so JOIN conditions are visible. Zero behavior change — purely readability. Don't touch the query logic.

### `cli.py` — 605 lines of registration boilerplate

Down from 719 lines in the pre-cleanup evaluation, but still 56 function definitions, nearly all 3-line thin wrappers: `@decorator → async def name(app, ...) → await _commands.cmd_name(app, ...)`. This is idiomatic Click, not wrong, but the density makes adding a new command feel like searching for the right insertion point in a wall of text. The only structural improvement that would help is grouping decorators consistently and using blank lines between command groups more deliberately. Not urgent, not blocking.

### `HestiaConfig` has 19 nested config objects

`config.py` at 412+ lines with 19 sub-configs. Each one is fine individually, but the aggregate mass is a signal that `HestiaConfig.from_file()` / `HestiaConfig.default()` are getting complicated. No structural change needed for v0.11.0, but if the config keeps growing, consider grouping into `HestiaConfig.core`, `HestiaConfig.platforms`, `HestiaConfig.features` sub-namespaces.

### `TokenBucket` single-event-loop assumption (core/rate_limiter.py)

`TokenBucket.consume` reads and writes `self.tokens` and `self.last_update` without a lock. This is safe under asyncio's single-threaded model but would break if a future change wraps a rate-limit check in `asyncio.to_thread`. Add a comment documenting the assumption.

---

## Summary: what to fix before tagging

**Must fix (bugs):**
1. `AppContext.close()` checks wrong attribute name (`_inference` instead of `inference`). Resource leak in CLI and scheduler modes.
2. `ToolExecutionError` missing from `classify_error` mapping. Tool failures misclassified as `UNKNOWN` in failure analytics.

**Should fix (cosmetic / correctness):**
3. Remove duplicate `# noqa: BLE001` from `doctor.py` lines 62, 235, 439.
4. Remove the `_italic_repl` item from the pre-release checklist — it's not dead code.

**Nice to fix (not blocking):**
5. Deduplicate `ConfirmCallback` type alias (defined in both `engine.py` and `execution.py`).
6. Comment the serial-vs-concurrent tool exception handling asymmetry in `execution.py`.
7. Fix the "reentrant-safe" comment in `slot_manager.py` line 229.
8. Add max-size eviction to `SessionRateLimiter._buckets`.
9. Move `import re` to module level in `telegram_adapter.py`.
10. Type `ReflectionRunner._on_failure` as `Callable` instead of `Any`.
11. Reformat `style/builder.py` SQL for readability.
12. Extract `PLATFORM_SCHEDULER` constant or delete the dead `session.platform == "scheduler"` check in `default.py` line 258.
13. Add STARTTLS comment in `email/adapter.py` explaining the exception propagation path.
14. Promote `_record_egress` failure logging from `logger.debug` to `logger.warning` (or at least `logger.info`).
15. Add comment to `TokenBucket` documenting the single-event-loop thread-safety assumption.

**Post-v0.11.0 (next arc):**
16. Streaming inference + progressive Telegram delivery (see streaming section above for implementation sketch and Kimi instructions).
17. Token counting batch optimization — single `count_request` for full message list instead of N per-message calls.
18. `hestia audit run --strict` subcommand for CI/health-check use.
19. Clarify `hestia doctor` vs `hestia audit` overlap in help text.
20. Consider `HestiaConfig` sub-groupings if config keeps growing (currently 19 nested config objects).
21. `cli.py` (605 lines) — better blank-line grouping between command groups for navigability.

---

## Kimi Loop Guidance — What Needs Better Instructions

Based on what went well and what went wrong in L60–L74, here's what future loop specs should be more explicit about:

**1. `cached_property` cleanup patterns.** The `close()` bug happened because the spec didn't specify how to check for lazily-created resources. Any loop touching `AppContext` lifecycle should include: "Use `'attr_name' in self.__dict__` to check whether a `functools.cached_property` has been materialized. Do NOT use `hasattr()` — it triggers the descriptor and creates the resource."

**2. Lock semantics in comments.** The slot manager "reentrant-safe" comment was wrong but the code was correct. Loops touching async lock management should specify: "asyncio.Lock is NOT reentrant. If you release and re-acquire within the same method, document the invariant that makes the finally block correct. Do not claim reentrancy."

**3. `classify_error` must be updated when adding new error types.** Any loop that adds a new `HestiaError` subclass should include: "Add the new error type to the `mapping` dict in `classify_error()` in `errors.py`. Add a test asserting the classification."

**4. Serial vs concurrent tool exception handling.** The current asymmetry is defensible but undocumented. Any loop touching `_execute_tool_calls` should specify: "Serial tools propagate exceptions to fail the turn (intentional — these are confirmation-gated tools). Concurrent tools catch exceptions per-tool. Document this in a code comment if it's not already there."

**5. Streaming is a cross-cutting concern.** Don't spec it as "add streaming to Telegram." Spec it as three incremental changes: (a) `InferenceClient.chat_stream()` that yields content deltas, (b) orchestrator streaming callback plumbing, (c) platform adapter wiring. Each can be a separate loop with a clear handoff.

---

## Verdict

The codebase is in good shape for a v0.11.0 tag. Items #1 and #2 in the must-fix list are both one-line fixes and should be done before tagging. Everything else is either cosmetic, a future-arc item, or a design decision that's defensible as-is.

Both audits converge on the same conclusion: the pre-release blockers are addressed. The kimi code review's three medium-severity findings (M1, M2, M3) are all resolved by L60–L74. The copilot evaluation confirmed every pre-release checklist item and found no crash risks or security holes. The remaining issues across both audits and this review are concentrated in monitoring accuracy (`ToolExecutionError` classification, egress log level), daemon memory hygiene (rate limiter buckets), and code readability (`style/builder.py`, `cli.py`).

The codebase is materially better than a month ago. The core loop is clean, the lifecycle management is correct, the security posture is strong by default. The code reads like it was written by someone who understands the operational constraints (consumer GPU, limited VRAM, long-running daemon) and has made deliberate engineering choices rather than reaching for defaults. The trust ladder, context budgeting, and meta-tool pattern are all real innovations for this problem space, not features bolted on for a checklist.
