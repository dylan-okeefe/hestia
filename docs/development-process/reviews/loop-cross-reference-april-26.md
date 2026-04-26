# Loop Cross-Reference: Three Evaluations vs. L60–L74

**Date:** April 26, 2026
**Sources:** Claude full evaluation, Copilot evaluation 1, Copilot evaluation 2
**Target:** 15 Kimi loop specs (L60–L74) on `feature/structural-cleanup-apr-26`

This document maps every actionable finding from all three evaluations to its loop coverage, identifies gaps, and recommends specific improvements.

---

## Part 1: Coverage Map

Each finding is tagged with its source (Claude, C1 = Copilot 1, C2 = Copilot 2) and its loop coverage.

### Fully Covered

| Finding | Source | Loop | Section |
|---------|--------|------|---------|
| `allowed_roots` default permissive | Claude, C2 | L63 | §1 |
| `EmailConfig.password` repr exposure | Claude, C2 | L63 | §2 |
| `developer()` preset no runtime guard | Claude, C2 | L63 | §3–§4 |
| InferenceClient 7 copy-pasted try/except | Claude, C1, C2 | L64 | §1 |
| InferenceClient missing context manager | Claude, C1, C2 | L64 | §2 |
| InferenceClient lifecycle not wired into app.py | Claude | L64 | §3 |
| SlotManager N+1 DB queries in eviction | Claude, C2 | L65 | §1 |
| SlotManager lock held across HTTP I/O | Claude, C2 | L65 | §2 |
| SlotManager silent 400 on slot_save | Claude, C2 | L65 | §3 |
| Meta-tool open-coded type switch | Claude, C1, C2 | L66 | §1 |
| `_message_to_dict` in wrong module | Claude, C1, C2 | L66 | §2 |
| `_tokenize_cache` unbounded | Claude, C2 | L67 | §1 |
| `_last_edit_times` unbounded | Claude, C2 | L67 | §2 |
| `_join_overhead` recomputation | Claude | L67 | §3 |
| Tag substring matching bug | Claude, C2 | L68 | §1–§2 |
| `hasattr` dead code in `_row_to_memory` | Claude | L68 | §3 |
| User-scope SQL duplication in MemoryStore | Claude | L68 | §4 |
| 40 unacknowledged `except Exception` | Claude, C2 | L69 | §1–§2 |
| `_italic_repl` dead code | Claude, C1, C2 | L70 | §1 |
| `_md_to_tg_html` regex soup | Claude, C2 | L70 | §2 |
| `test_builtin_tools_new.py` duplicate | C1, C2 | L70 | §3 |
| App context three-class hierarchy | Claude, C1, C2 | L71 | §1 |
| `make_app()` 150-line monolith | Claude, C1 | L71 | §3 |
| curl_cffi fallback weakens SSRF | Claude, C2 | L72 | §2 |
| No tool-call-per-turn cap | Claude, C2 | L72 | §1 |
| Skills subsystem incomplete | Claude, C2 | L73 | §1 |
| Reflection over-engineered | Claude | L73 | §2 |
| Style profile over-engineered | Claude | L73 | §3 |
| No `hestia history` command | Claude | L74 | §1 |
| No startup config validation | Claude, C2 | L74 | §2 |

### Partially Covered (loop touches the area but misses specific items)

| Finding | Source | Nearest Loop | What's Missing |
|---------|--------|-------------|----------------|
| `bot_token` repr exposure in exceptions | C2 | L63 (§2 covers email only) | Telegram bot token same risk as email password — appears in `repr()`, stack traces |
| FTS5 `_sanitize_fts5_query` incomplete for `*`, `^`, `NOT` operators | C2 | L68 (covers tag matching) | L68 fixes tag substring but doesn't address the FTS5 query sanitizer letting through `*`, `^`, and `NOT` without space separators |
| User-facing error messages are developer-centric | C2 | L69 (exception handling) | L69 is about catching and logging; doesn't address the user-visible side — "Something went wrong" is too vague, non-Hestia errors show raw class names |
| `get_or_create_session` TOCTOU under Postgres | Claude, C2 | L65 (concurrency) | L65 covers SlotManager only; the session store race is a separate concurrency concern |
| Email adapter connection lifecycle fragile | Claude | L64 (lifecycle) | L64 covers InferenceClient only; EmailAdapter has the same pattern of unhealthy connection management |

### Not Covered in Any Loop

These items appeared in one or more evaluations but have zero loop coverage:

| # | Finding | Source | Severity | Recommendation |
|---|---------|--------|----------|----------------|
| 1 | `egress_events` table stores full URLs including credentials (API keys, tokens in query strings) | Claude | Medium | Add to L72 — same security boundary as SSRF |
| 2 | `list_dir.py` per-item `asyncio.to_thread` — 300 thread pool dispatches for a 100-file directory | Claude, C2 | Low | Add to L67 — daemon stability / efficiency theme |
| 3 | Token counting HTTP round-trip per message — no batching; 50 history messages = 50 POST /tokenize | Claude | Medium | Add to L67 or create standalone perf loop |
| 4 | Inconsistent tool factory patterns (`@tool` functions vs `make_*_tool` factories) | Claude | Low | Add to L66 — extensibility theme |
| 5 | `cli.py` 695 lines of pure command registration boilerplate | Claude | Low | Add to L71 — same "structural overhead" theme |
| 6 | Pydantic `BaseModel` mixed with dataclasses (`FunctionSchema`, `ToolSchema` vs everything else) | Claude, C2 | Low | Informational — defer unless touching `core/types.py` |
| 7 | `ArtifactStore.get()` synchronous reads (writes use `asyncio.to_thread`, reads don't) | Claude | Low | Add to L67 — daemon hygiene theme |
| 8 | No streaming inference support | C2 | Low (feature) | Future loop — not a bug or cleanup item |
| 9 | No per-user/session rate limiting | C2 | Medium (feature) | Add to L72 as §3 — same boundary-enforcement theme |
| 10 | No metrics/observability export (Prometheus, OpenTelemetry) | C2 | Low (feature) | Future loop — infrastructure concern, not cleanup |
| 11 | No graceful platform-add path (adding a new platform requires touching too many files) | C2 | Low | Could fold into L71 (structural) but low priority |
| 12 | `_compile_and_set_memory_epoch` potential duplication across modules | Claude | Low | Needs verification first — grep before creating work |
| 13 | SlotManager concurrency stress tests | C2 | Medium (testing) | L65 acceptance hints at it but doesn't mandate it |
| 14 | `_sanitize_fts5_query` test coverage for `*`, `^` operators | C2 | Medium (testing) | Should be in L68 acceptance criteria |
| 15 | croniter lazy import pattern (unnecessary) | C2 | Trivial | Not worth a loop — fix opportunistically |

---

## Part 2: Recommended Improvements to Existing Loops

### L63 — Security Defaults & Trust Hardening

**Add §2a: `bot_token` repr redaction**

L63 §2 correctly addresses `EmailConfig.password` repr exposure, but the Telegram `bot_token` has the identical risk. It appears in `TelegramConfig` as a plain `str` field and will show up in `repr()`, stack traces, and debug logs the same way.

Suggested addition:
```
### §2a — TelegramConfig.bot_token repr redaction

**File:** `src/hestia/config.py`
Add `__repr__` to `TelegramConfig` that masks `bot_token`.
Same pattern as §2 for EmailConfig.

**Commit:** `fix(config): redact bot_token in TelegramConfig repr`
```

Add to acceptance: "`repr(telegram_config)` does not contain the literal bot token string."

---

### L64 — InferenceClient Consolidation & Resource Lifecycle

**Add §4: Email adapter connection lifecycle**

L64 correctly targets InferenceClient, but my evaluation identified the same lifecycle fragility in `EmailAdapter` (556 lines, IMAP connections with partial-failure edge cases, no `async with` support). The connection create/select/operate/close flow has multiple `try/except` blocks that can leave connections in unclear states.

Since L64's theme is "resource lifecycle," this is a natural fit:

```
### §4 — EmailAdapter connection lifecycle

**File:** `src/hestia/email/adapter.py`
Audit IMAP/SMTP connection management for partial-failure states.
Ensure connections are context-manager friendly and closed cleanly
on shutdown or error.

**Commit:** `fix(email): clean up connection lifecycle in EmailAdapter`
```

---

### L65 — SlotManager Concurrency & Correctness

**Strengthen acceptance criteria for concurrency testing**

The intent-based acceptance says "Verify by timing `acquire()` under synthetic load" but doesn't mandate this as a test artifact. Copilot 2 specifically flagged the absence of SlotManager concurrency stress tests. Add:

```
## Additional Acceptance
- A test file `tests/integration/test_slot_manager_concurrency.py` exists
  with at least: (a) concurrent acquire() calls, (b) mock slow slot_erase
  verifying no stall, (c) simulated 400 on slot_save verifying COLD state.
```

**Add §4: `get_or_create_session` TOCTOU under PostgreSQL**

The partial unique index + ON CONFLICT approach is sound for SQLite but needs verification under PostgreSQL concurrent load. This is a concurrency concern that fits L65's theme:

```
### §4 — Verify get_or_create_session under concurrent PostgreSQL load

**File:** `src/hestia/persistence/sessions.py`
The ON CONFLICT WHERE clause requires the partial index to exist.
Verify the migration path and test under concurrent session creation.
If PostgreSQL is not currently a supported backend, document this
limitation explicitly.

**Commit:** `test(sessions): verify get_or_create_session under concurrent load`
```

---

### L66 — Meta-Tool Extensibility & Serialization Hygiene

**Add §3: Unify tool factory patterns**

My evaluation noted that tools use two inconsistent patterns: plain `@tool` decorated functions (`current_time`, `http_get`, `terminal`) and factory functions that return decorated functions (`make_read_file_tool(storage_config)`, `make_search_memory_tool(memory_store)`). The naming convention (`make_*_tool` vs plain function) is inconsistent.

This fits L66's extensibility theme:

```
### §3 — Standardize tool construction patterns

**Files:** `src/hestia/tools/builtin/*.py`
Audit and document the two patterns. Either:
(a) Standardize on factories for all tools that need dependencies,
    with a consistent naming convention.
(b) Introduce a dependency-injection pattern so all tools use @tool
    and declare dependencies the registry resolves.

The current mix is not broken, but it creates confusion about which
pattern to use when adding new tools.

**Commit:** `refactor(tools): document or standardize tool construction patterns`
```

---

### L67 — Bounded Caches & Daemon Stability

**Add §4: `list_dir.py` per-item `asyncio.to_thread`**

Both my evaluation and Copilot 2 noted that `list_dir.py` calls `asyncio.to_thread` for each `is_dir()`, `is_file()`, `stat()` on each directory entry. A directory with 100 files means ~300 thread pool dispatches. The entire directory scan should be a single `asyncio.to_thread` call.

```
### §4 — Batch list_dir filesystem calls

**File:** `src/hestia/tools/builtin/list_dir.py`
Wrap the entire directory iteration in a single asyncio.to_thread
call instead of per-item dispatches.

**Commit:** `perf(list_dir): batch filesystem calls into single thread dispatch`
```

**Add §5: Token counting batching opportunity**

My evaluation noted that `ContextBuilder._count_tokens()` makes an HTTP POST to `/tokenize` per message. On a fresh turn with 50 history messages, that's 50 HTTP round-trips just for token counting. Most llama.cpp servers can handle batch tokenization, and system prompt / identity / memory epoch token counts are nearly static.

```
### §5 — Explore token counting batching

**File:** `src/hestia/context/builder.py`
Investigate whether the llama.cpp /tokenize endpoint supports batch
requests. At minimum, pre-compute and permanently cache token counts
for static content (system prompt, identity, memory epoch) since
these change at most once per session.

**Commit:** `perf(context): cache static-content token counts`
```

---

### L68 — Memory Store Precision & Maintainability

**Add §5: FTS5 query sanitizer escaping for `*`, `^`, `NOT`**

Copilot 2 specifically noted that `_sanitize_fts5_query` escapes double quotes and strips some operators, but doesn't handle `*` (prefix match), `^` (boost), or `NOT` without a preceding space. These can alter query semantics or cause FTS5 parse errors on untrusted input.

```
### §5 — Complete FTS5 operator escaping in _sanitize_fts5_query

**File:** `src/hestia/memory/store.py`
Extend _sanitize_fts5_query to handle:
- `*` (prefix match operator) — strip or escape
- `^` (boost operator) — strip or escape
- `NOT` without space separation — ensure proper tokenization

Add test cases for each operator in untrusted input.

**Commit:** `fix(memory): complete FTS5 operator escaping in query sanitizer`
```

Add to acceptance: "A test asserts that `_sanitize_fts5_query('work*')` does not perform a prefix match on unrelated terms. A test asserts that `'^important'` does not boost. A test asserts that `'catNOTdog'` is not interpreted as a NOT query."

---

### L71 — App Context Gravity Well

**Add §4: `cli.py` boilerplate reduction**

My evaluation noted that `cli.py` at 695 lines is almost entirely command registration wiring — thin wrappers that delegate to `commands/`. Every CLI command is:

```python
@group.command(name="foo")
@click.option(...)
@click.pass_obj
@async_command
async def foo(app, ...): await cmd_foo(app, ...)
```

This is the same "structural overhead" theme as the app context hierarchy. With 50+ commands, adding a new one means editing two files when it could be one.

```
### §4 — Reduce cli.py registration boilerplate

**File:** `src/hestia/cli.py`
Consider auto-discovery (click supports adding commands from a
package) or a declarative registration pattern. At minimum,
document why the two-file pattern exists and whether it can be
collapsed.

**Commit:** `refactor(cli): reduce command registration boilerplate`
```

---

### L72 — Tool Call Boundaries & SSRF Defense

**Add §3: Strip credentials from egress_events URLs**

My evaluation noted that `egress_events` stores full URLs. If the model calls `http_get` on a URL with credentials in the query string (API keys, tokens), those are persisted in cleartext to the audit log.

```
### §3 — Sanitize URLs in egress_events

**File:** `src/hestia/tools/builtin/http_get.py` (or `persistence/trace_store.py`)
Strip or redact query parameters from URLs before writing to
egress_events. At minimum, redact known credential patterns
(api_key, token, secret, password, key). Alternatively, store
only scheme + host + path.

**Commit:** `fix(http_get): redact query credentials from egress audit log`
```

**Add §4: Per-user/session rate limiting consideration**

Copilot 2 flagged the absence of per-user or per-session rate limiting. L72 §1 caps tool calls per turn, but there's no protection against a user firing 100 turns per minute. This fits the boundary-enforcement theme:

```
### §4 — Per-session turn rate limiting (design only)

Document the design for per-session or per-user rate limiting.
This need not be implemented in this loop, but the config field
and enforcement point should be identified. Likely location:
`Orchestrator.process_turn()` with a `max_turns_per_minute`
field in `TrustConfig`.

**Commit:** `docs: design note for per-session rate limiting`
```

---

### L74 — UX Gaps & Config Validation

**Add §3: User-facing error message improvement**

Copilot 2 noted that error messages shown to end users are developer-centric. L69 addresses exception handling and logging transparency, but doesn't address what the user actually sees. The `sanitize_user_error` function in finalization exists but is blunt — non-`HestiaError` exceptions become "Something went wrong" with no actionable guidance.

```
### §3 — Improve user-facing error messages

**File:** `src/hestia/orchestrator/finalization.py`
Audit sanitize_user_error for actionability. Where possible,
map common failure classes to user-friendly messages:
- Inference timeout → "The AI is taking longer than expected. Try again."
- Tool error → "I tried to use [tool] but it failed. [brief reason]."
- Context too large → "Our conversation is very long. I'll summarize and continue."

**Commit:** `feat(ux): improve user-facing error messages`
```

---

## Part 3: Items to Defer

These appeared in evaluations but are either feature requests, informational, or low-priority enough to skip in this cleanup arc:

1. **No streaming inference** (C2) — Feature, not cleanup. Worth a future loop when the llama.cpp streaming API is stable.
2. **No metrics/observability export** (C2) — Infrastructure concern. Worth doing but doesn't belong in a cleanup arc.
3. **No web UI** (Claude) — ADR-007 explicitly defers this. Correct call.
4. **No graceful platform-add path** (C2) — Low priority. The current process (copy an adapter, wire it in) works for the frequency of new platforms.
5. **Pydantic mixed with dataclasses** (Claude, C2) — Cosmetic inconsistency. Not worth the churn unless `core/types.py` is being rewritten for other reasons.
6. **croniter lazy import** (C2) — Trivial. Fix opportunistically if touching the scheduler.
7. **`_compile_and_set_memory_epoch` duplication** (Claude) — Needs a grep to verify. If confirmed, it's a one-line fix, not worth a loop section.
8. **`ArtifactStore.get()` synchronous** (Claude) — Minor inconsistency. Fix if touching the file for other reasons.

---

## Part 4: Summary of Recommended Changes

### Additions to existing loops (11 items):

| Loop | New Section | What |
|------|------------|------|
| L63 | §2a | `bot_token` repr redaction |
| L64 | §4 | Email adapter connection lifecycle |
| L65 | §4 | `get_or_create_session` concurrency verification |
| L65 | Acceptance | Mandate concurrency stress test file |
| L66 | §3 | Standardize tool factory patterns |
| L67 | §4 | `list_dir.py` batch thread dispatch |
| L67 | §5 | Token counting batching / static caching |
| L68 | §5 | FTS5 operator escaping (`*`, `^`, `NOT`) |
| L71 | §4 | `cli.py` boilerplate reduction |
| L72 | §3 | Egress URL credential stripping |
| L72 | §4 | Per-session rate limiting design note |
| L74 | §3 | User-facing error message improvement |

### Items to defer (8 items):

Streaming inference, metrics export, web UI, platform-add path, Pydantic/dataclass mix, croniter import, memory epoch duplication (verify first), ArtifactStore sync reads.

### Net assessment:

The loop specs are thorough — roughly 80% of findings across all three evaluations are fully covered. The gaps are concentrated in two areas: (a) security items that are adjacent to but not included in existing loops (bot_token redaction, egress URL credentials, FTS5 escaping), and (b) efficiency/daemon-hygiene items that are small enough to have been overlooked (list_dir threading, token batching, ArtifactStore reads). None of the gaps are critical blockers, but the security-adjacent items (L63 §2a, L68 §5, L72 §3) should be folded in before those loops execute.
