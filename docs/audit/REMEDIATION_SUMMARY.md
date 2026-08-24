# Audit Remediation Summary — `feature/audit-remediation-r1`

**Date:** 2026-08-23 · **Base:** runtime branch @ `4388cc9c`
**Scope:** every audit finding that could be fixed without an operator decision.
**Verification at final commit:** ruff clean · mypy 0 errors (226 files) · pytest 2,281 passed / 6 skipped (~140 s) · `npm run build` green · vitest 132/132 · inline-style count 11 (< 20 budget).

Commits, oldest first:
1. `fix(quality): restore green gates` — ruff 49→0, mypy 7→0, TS build fixed (BUG-049), webhook-secret UI flow wired to rotate endpoint (SEC-013 UI half)
2. `fix(concurrency): close session-lock pop race and slot-eviction race` (BUG-001/002)
3. `fix(inference): honest streaming failures` (BUG-003/022/046, PERF-004)
4. `fix(orchestrator): thinking budget + transient retries` (BUG-020/021) + RETRYING transition
5. `fix(context): window grouping, dangling-call repair, splice revalidation` (BUG-027/072/019/028)
6. `fix(memory/orchestrator): maintenance safety, token accounting, journaling` (BUG-010/011/026/031/073/074/076/079/080/081, SEC-018)
7. `fix(persistence): pragmas, indexes, m006 dialect guard, bootstrap lock, retention` (BUG-008*/009/068/075, PERF-005/006)
8. `fix(platforms)` — voice confirmations/channel (BUG-014/062/063), markdown fallback (BUG-015), Matrix parity (BUG-032/065/066), allowlist normalization (BUG-064), email resilience (BUG-017/018/033), serve lifecycle (close_inference param; BUG-035 sweep)
9. `fix(workflows)` — SEC-001 gating, execution lifecycle RUNNING rows + crash sweep (BUG-036), self-trigger refusal (BUG-004), cron heartbeat + strict matchers (BUG-005/SEC-021), test isolation (BUG-041), loud LLM-decision failures (BUG-038), skipped NodeResults (BUG-039), HTTP-node cap+egress (BUG-040), interpolation honesty (BUG-069), condition short-circuit (BUG-070), destination precedence (SEC-022), versions-API secret redaction (SEC-014), PERF-017
10. `fix(web+tools)` — SEC-002/023 login recipient allowlisting, roster minimization (SEC-026), debug_login guard (SEC-006), topic IDOR (SEC-007), scheduler admin parity (BUG-082), fs tools atomic/bounded (PERF-011a/b), terminal env-allowlist/output-cap/timeout-clamp (SEC-015)
11. `fix(web-ui)` — work-loss pair (BUG-055/056/057), polling hygiene (BUG-050..053), root ErrorBoundary (BUG-058), doctor/audit catches (BUG-054), Defer button (D6), a11y bundle (A1/A2/A4/A5), editor/papercut fixes (BUG-084..087), SEC-002 picker change
12. `chore: remove dead code` (BUG-088 delete ×2, alias validator, is_ssrf_blocked, _BLOCKED_RANGES + its test, publish_nowait fallback (BUG-029), CliPlatform)

## Choices made (flagged for review)

1. **Streaming stall now FAILS the turn** (raises InferenceTimeoutError) instead of delivering a truncated answer marked "stop" — mirrors non-streaming semantics already in the codebase. The partial answer that already streamed to the screen is ALSO persisted to history as an assistant message suffixed "[response interrupted — incomplete]", so what the user saw and what the model remembers stay in sync (review follow-up).
2. **Retries are non-streaming-only.** Streaming turns fail fast on transient errors because partial text was already delivered and a retry would duplicate it in stream state.
3. **Foreign keys remain OFF.** Measured 89 pre-existing FK violations in the live DB; enabling checks before cleanup would risk runtime failures. WAL + busy_timeout applied per connection instead.
4. **Cron workflows fire via a per-minute scheduler heartbeat**, not first-class task registration (smaller, no user-visible scheduled_tasks clutter). Cron-less and command-less triggers now never match.
5. **Login picker UX**: platform buttons come from the unauthenticated roster's platform *names* (chat IDs removed). If a selected user lacks an identity on that platform, request fails with a generic error.
6. **Matrix commands now require exact token match** (`/resetnow` is no longer `/reset`) but trailing arguments still dispatch, matching Telegram.
7. **Email poison messages park after 5 failures** (marked read, logged as errors). At-least-once semantics otherwise preserved.
8. **Terminal child processes get an env allowlist** (PATH/HOME/USER/SHELL/TERM/TMPDIR/locale). Commands needing other vars will not see them — intentional secret-exfiltration fix.
9. **test executions persist flagged `is_test`** and are excluded from last-execution aggregates but remain visible in per-workflow history.
10. **Kept despite being dead in src:** `TelegramConfig.fallback_ips`/timeout fields (removal could TypeError external config files this worktree can't see) and `Database.execute()` (tests use it).

## Deliberately NOT done (needs your decision)

- BUG-044 auth-code digit filter scoping (reverses a deliberate privacy choice?)
- BUG-023 `/reset` cancellation semantics; BUG-045 💭 prefix presentation; reset-semantics unification TG-vs-MX
- Workflow duration ceilings/cancel endpoint values; SUBAGENT channel trust classification (F4); curl_cffi model-selectability (SEC-011); structured injection-flag propagation (SEC-012); webhook replay persistence (SEC-017)
- Delta tokenization cache (PERF-003) — needs careful design; bundle route-splitting beyond current work; openui removal
- Retention windows for traces/capability_events/egress (maintenance_trace TTL is wired; others need window decisions)
- FK violation cleanup (89 rows) before enabling enforcement
- escape_room_planning.md removal from git (your file)

## Board note

TaskView cards could not be created from this environment (no board API access here). This summary + commit list maps 1:1 to cards if you want them mirrored; recommend moving straight to In Review.

## Follow-through: L245 allowlist-only authorization (card #44)

The F5 finding (allow-lists advisory; four ungated paths) was remediated
in a dedicated loop on `feature/l245-gate-chokepoint`, tracked in
`docs/development-process/loops/L245-gate-chokepoint.md` and recorded in
`docs/adr/ADR-052-allowlist-only-tool-authorization-for-unattended-channels.md`:

- Registry-level chokepoint with required `ToolCallContext` (strict mode);
  the four bypass paths route through gated dispatch.
- Workflow grants are graph-derived (`derive_allowed_set`), confirmed via
  an activation diff (409 + confirm flag), and enforced for node effects;
  migration m011 backfills existing rows.
- Scheduler TrustConfig flags now gate SCHEDULER-channel turns for real.

Verification at final L245 commit: ruff clean · mypy clean · pytest
2,312 passed / 6 skipped · vitest 135/135 · `npm run build` green ·
inline-style count 11 (< 20 budget).
