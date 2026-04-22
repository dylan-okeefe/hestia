# Kimi code review — develop, v0.9.x train

**Date:** 2026-04-22
**Scope:** Everything Kimi landed on `develop` since the v0.8.0 release: L40 copilot-cleanup, L41 voice-shared-infra, L42 voice-phase-a-messages, L45a-c identity/memory/multi-user, v0.9.0 hotfix bundle, v0.9.1 bundle. **Excludes** `discord_voice_runner.py` (already reviewed under L46).

**Method:** Delegated initial trawl to a subagent, then verified every claim against the actual code before including it here. Several subagent findings turned out to be wrong — those are listed at the bottom so this doc doesn't silently vanish them.

## TL;DR

The v0.9.x merges are in much better shape than the Discord voice iteration. The worst I found is one real correctness issue in memory save (orphan scope), one incomplete refactor cosmetic, and one subtle exception propagation risk in the concurrent-tool path that wants a belt-and-suspenders `return_exceptions=True`. Nothing blocking. No evidence of "fixed in code — needs validation" lying in the non-voice code. The discord voice work was the outlier, not the norm.

## Verified findings

### M1 — Memory.save silently writes an orphan row when called outside an orchestrator context

**File:** `src/hestia/memory/store.py:169–229`
**Severity:** Medium.

`save()` falls back to `_get_user_scope()` when `platform`/`platform_user` are not passed. If the caller is outside the orchestrator (CLI scripts, a REPL poke, a scheduler tick before the ContextVar is set, a test harness that didn't set the ContextVars), both ContextVars return `None`. The row is inserted with `platform=NULL, platform_user=NULL`. Scoped queries later won't find it — the scope join in `search()` is `AND platform = :platform AND platform_user = :platform_user`, which doesn't match NULLs.

**Why it matters:** A tool call that invokes `memory_save` from a background context (e.g. a scheduler "remember this" task where someone forgot to set the identity ContextVars) will write a ghost row the owner never sees. No warning, no error.

**Fix sketch:**
```python
if platform is None or platform_user is None:
    ctx_platform, ctx_platform_user = self._get_user_scope()
    platform = platform or ctx_platform
    platform_user = platform_user or ctx_platform_user
if platform is None or platform_user is None:
    logger.warning(
        "memory.save called outside an identity context; "
        "saving as unscoped (platform=%r, platform_user=%r)",
        platform, platform_user,
    )
```

Two-line change, makes the silent failure loud.

### M2 — Memory.search loses scope when only one of platform/platform_user is set

**File:** `src/hestia/memory/store.py:258–304`
**Severity:** Medium.

The branch condition is `if platform is not None and platform_user is not None:` (line 260, 285). If exactly one is set, the code falls through to the *unscoped* query, returning memories across all users. This is the opposite of fail-closed.

Same fix as M1: if only one is set, log and either reject or fall through with both `NULL`. Returning "everyone's memories" to a partially-identified caller is the worst outcome because it silently leaks isolation.

### M3 — `_execute_tool_calls` propagates exceptions out of `asyncio.gather`

**File:** `src/hestia/orchestrator/engine.py:718–721`
**Severity:** Medium (risk, not a confirmed bug).

```python
for idx, result in await asyncio.gather(
    *[_run_one(i) for i in concurrent_indices]
):
    concurrent_results[idx] = result
```

`asyncio.gather(...)` without `return_exceptions=True` raises on the first failure and cancels the remaining siblings. `registry.call()` catches broad `Exception` and returns `ToolCallResult.error(...)`, so the common path is fine. But `_dispatch_tool_call` calls `_check_confirmation` and `_tools.describe` *before* reaching `registry.call` — if either of those raises (e.g. confirmation callback throws, describe hits a registry race), the exception escapes `_run_one` and the whole `gather` explodes, killing any concurrent tools that were already mid-flight.

**Why it matters:** An HTTP timeout in a confirmation callback would turn an in-flight web search into a canceled future *and* a failed turn — rather than "the one tool that needed confirmation errored out, the other three tools completed fine".

**Fix:** either wrap `_run_one`'s body in `try/except` and return a `ToolCallResult.error(...)`, or pass `return_exceptions=True` to gather and materialize exceptions into results in the reassembly loop. I'd do the former — it's 4 lines and keeps the gather signature boring.

### L1 — Incomplete M-12 constant extraction

**File:** `src/hestia/policy/default.py:249` and `src/hestia/policy/constants.py`
**Severity:** Low (cosmetic — no runtime issue).

Commit `77569f3` (M-12 refactor) claims "extract PLATFORM_* constants." In practice only `PLATFORM_SUBAGENT` was extracted. Line 249 still reads `if session.platform == "scheduler" or scheduler_tick_active.get():`. Nothing actually creates sessions with `platform="scheduler"` anywhere in the codebase, so the literal is dead-ish defensive code — but the commit message overstated what shipped.

**Fix:** either delete the `session.platform == "scheduler"` half (it's unreachable given current session creation sites), or extract `PLATFORM_SCHEDULER` and `PLATFORM_CLI` to constants.py and use them consistently.

### L2 — Session-collision retries log at DEBUG

**File:** `src/hestia/persistence/sessions.py:320–330` and `532–542`
**Severity:** Low.

The L45a hotfix for TOCTOU on `get_or_create_session` is correct — it does an insert, catches `IntegrityError`, and re-selects. The retry is logged at `debug`. Under contention that's invisible by default. This isn't a bug per se, but if you ever get race-condition weirdness in session creation, you'll have no operational signal. Consider INFO, or add a counter.

### L3 — `VoicePipeline._ensure_stt_loaded` uses a single lock for both STT and TTS init

**File:** `src/hestia/voice/pipeline.py:42`
**Severity:** Low.

```python
_init_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
```

Both `_ensure_stt_loaded` and `_ensure_tts_loaded` grab the same lock. If a first caller is loading the ~1.6 GB Whisper model while a second caller needs TTS, the TTS caller waits for the entire STT download. In practice both are one-shot startup costs, so the impact is "TTS starts late once, ever" — minor. A two-lock design would be slightly nicer but isn't worth a rewrite.

## Explicit "no finding" notes

- **L41 voice pipeline** — clean. PCM→WAV header math checks out, sentence splitter regex is fine for v1, Piper voice loading path is correct.
- **L42 Telegram voice** — clean. ffmpeg subprocess error paths raise, outer `try/except` converts to user-facing text messages, temp-file cleanup is in `finally` and reachable on every return path.
- **L45a runtime identity** — clean. ContextVar set/reset is in try/finally around `process_turn`; the test suite includes failure-path lifecycle coverage.
- **L45c allowlist** — clean. `fnmatch` usage, case-sensitivity split, empty-list-denies-all invariant are all correct. 29 tests.
- **v0.9.0 hotfix bundle** (H-1/2/3/4/9, C-3/4/5/6, A-3) — clean. STARTTLS response check is verified (line 130–137), `SMTP_SSL` branch on port 465 is verified, artifact async offload (`aiofiles`) is verified, inference-server typed errors are verified.
- **v0.9.1 bundle** — clean except M-12 (see L1). The IMAP `INTERNALDATE` sort (M-7) is correctly implemented; the in-memory history accumulator (M-2) correctly resets per turn; the FTS5-vs-LIKE parity test (T-8) actually asserts on behavior.

## Subagent claims that turned out to be wrong

Flagging these so they don't re-surface in future reviews:

- **"`TURN_RESPONSE_RESERVE_TOKENS` is imported but never defined in `constants.py`"** — False. The import at `default.py:9` only brings in `CONTEXT_PRESSURE_THRESHOLD` and `PLATFORM_SUBAGENT`. The literal `2048` at line 173 is intentional; M-6 was about `CONTEXT_PRESSURE_THRESHOLD`, not the reserve budget.
- **"Memory queries silently return empty when ContextVars are unset"** — False. When platform/platform_user are both None, `search()` falls through to the *unscoped* SQL and returns rows across users. The real bug is the opposite (isolation leak), captured as M2.
- **"Telegram voice temp-file cleanup is unsafe"** — False, and the agent caught itself. The `finally` block at `telegram_adapter.py:331–333` runs on every return path.
- **"Email adapter still hardcodes Drafts/Sent folders"** — False, and the agent caught itself. L40 wired through `config.drafts_folder` / `config.sent_folder` correctly.

## Priorities

Only M1 is worth patching before the README rewrite. M2 and M3 are worth a loop (call it L47-or-later) but not urgent. L1-L3 are cleanup during the next natural refactor.

If you want a single fast PR: M1 + M2 together, one commit, one test that poked `search`/`save` with `platform=None, platform_user="x"` and asserts on the fail-loud path. Thirty minutes of work.

## Loose observations (not findings)

- The L45a-c test suite is genuinely thorough — 14 tests for `_trust_for` alone, 29 for the allowlist. Kimi did this set of loops well.
- The v0.9.1 release checklist (`docs/releases/`) is complete and matches what actually shipped. Good release hygiene.
- No `run_coroutine_threadsafe` failures of the kind that bit the Discord voice runner. The pattern is simply not used outside the Discord worker thread.
- No `except: pass` anywhere in the reviewed scope. The bare-except sites I flagged in the 2026-04-21 audit are all pre-Kimi code.

## Sources

- `src/hestia/memory/store.py`
- `src/hestia/orchestrator/engine.py`
- `src/hestia/policy/default.py`, `src/hestia/policy/constants.py`
- `src/hestia/persistence/sessions.py`
- `src/hestia/voice/pipeline.py`
- `src/hestia/tools/registry.py`
- `src/hestia/platforms/telegram_adapter.py`
- `docs/handoffs/L40-copilot-cleanup-handoff.md`, `L41-voice-shared-infra-handoff.md`, `L42-voice-phase-a-messages-handoff.md`, `L45a-c-*-handoff.md`
