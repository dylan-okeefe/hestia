# Hestia — Comprehensive Audit: Executive Summary

**Audit date:** 2026-08-22 · **Worktree:** `~/Hestia-runtime` @ `4388cc9c` · **Scope:** full stack (backend ~41.7k LOC Python / React dashboard / tests / docs / live runtime), method = parallel deep subsystem exploration + direct verification of critical findings + measured runtime observation.
**Reading guide:** this file stands alone. Detail lives in `01`–`13`; the consolidated finding register with severity/confidence/evidence is `07_BUGS_RELIABILITY.md`; the actionable ordering is `12_PRIORITY_ROADMAP.md`.

---

## Overall state

Hestia is **substantially better-engineered than its bug count suggests, with two genuine holes that matter more than everything else combined**. The chat-agent core (turn state machine, token engineering, degeneracy defense, reversibility-by-construction memory) reflects real discipline and survived adversarial auditing well. The workflow engine — the newest major subsystem — is functionally immature and contains the audit's one Critical security finding. The process machinery (ADRs, loop specs, test culture) demonstrably works but has drifted: all three quality gates are currently red/broken on branch.

Counts: **~60 registered findings** — 2 Critical (one verified by direct inspection twice independently), ~19 High, rest Medium/Low; plus 16 performance items, ~20 UX/a11y items, 9 architectural weaknesses, 8 testing gaps. No finding requires a rewrite to fix; nearly all are surgical or bounded-milestone work.

## Strongest aspects (protect these)

1. **Turn state machine + journaling** — explicit transition table, journaled transitions, crash forensics that proved themselves in the Aug-13 llama-crash investigation.
2. **Token engineering** — server-truth `/tokenize` counting, content-hash prefix caches, reasoning stripped from history, calibration factors; best-engineered subsystem in the repo.
3. **Degeneracy defense** — five tailored circuit breakers with correction injection and regression-fixture capture; not generic retries.
4. **Reversibility-by-construction memory automation** — soft delete + undo windows + traces + digests honoring ADR-049 exactly.
5. **Security primitives where applied**: webhook HMAC textbook; SSRF transport validating every hop; fail-closed defaults everywhere (empty allowlists deny, unknown preset→paranoid, missing identity blocks search); confirmation requester-binding with double-submission safety.
6. **Test architecture** — fakes at true boundaries, real async SQLite, genuine 20-writer race tests, deterministic ~260 s suite of 2,272 tests with ADR-citing docstrings.
7. **Process/documentation discipline** — 51 ADRs matching shipped code unusually well; observability inventory (traces, failure bundles, egress log, doctor, digests) far above solo-project norm.

## Biggest weaknesses

1. **Trust boundary enforced by convention, not chokepoint** (`01` §ARCH-001). Four tool-invocation paths bypass CapabilityGate entirely — worst: workflow `tool_call`/`investigate` nodes execute arbitrary tools incl. `terminal` ungated, reachable via webhooks/chat commands (**SEC-001**, Critical). `workflow.trust_level`, scheduler allow-list flags, and the gate's own approval verdict are dead controls.
2. **Core concurrency invariant has a silent race** (**BUG-001**, Critical): lock-pruning pops dict entries during the asyncio unlocked-window between release and waiter resumption → two turns per session can run concurrently, voiding ADR-041 without any error. Slot eviction I/O races allocation similarly (**BUG-002**).
3. **Silent failure as default strategy** across every layer: stream stalls presented as complete answers (BUG-003), SSE errors stalling until timeout (BUG-022), interpolation resolving missing keys to `""`, skipped workflow nodes leaving no record, invalid LLM decisions yielding ok-with-vanished-graph, frontend discarding malformed JSON silently.
4. **Workflow execution semantics immature**: no RUNNING state/cancellation/duration ceiling/concurrency control; crash leaves no trace; `workflow_completed` self-trigger loops forever (BUG-004); cron triggers only fire when unrelated tasks happen to fire (BUG-005 — effectively broken); test runs execute production side effects (BUG-041).
5. **Frontend ships broken and heavy**: build fails on branch (BUG-049); single 800 KB-gzip chunk; any 401 instantly logs out destroying unsaved work (BUG-055); Save&Activate transient failures destroy unsaved graphs (BUG-056).
6. **Persistence untuned and drifting**: no WAL/busy_timeout/FKs (measured on live DB), no index on the hottest table, IN-clause binding crashes in two stores, PostgreSQL path effectively broken, timestamp idioms fragmented causing wrong scheduling comparisons.
7. **Duplication already billing interest**: WHERE-builders ×4 (two carry the same bug), edit rate-limiters ×2 (one leaks), reset flows ×2 (divergent semantics), command parsers ×2 (Matrix's is buggy).

## Most serious risks (ranked)

1. **SEC-001**: webhook/chat-triggered workflows running `terminal`/file/email tools unattended — directly contradicts the repo's central security claim.
2. **BUG-001/002**: serialization/slot races corrupting conversation state silently under ordinary multi-message load.
3. **Data-integrity cluster**: nightly maintenance deleting losers after failed merges (BUG-010), FTS5 crashes aborting passes (BUG-011), hard-delete memory tool contradicting undo posture, nine unbounded tables.
4. **User-trust erosion cluster**: voice turns auto-denying confirmations (BUG-014), markdown parse failures breaking gated tools mid-use (BUG-015), truncated answers presented as complete (BUG-003), Matrix typos destructively resetting sessions (BUG-032).
5. **Process risk**: red gates mean none of the above get caught at merge time — the same drift that let BUG-049 ship.

## Most valuable opportunities (highest leverage)

1. **Restore green gates + wire CI** (~1 day) — converts every other fix from vigilance into enforcement.
2. **Registry-level gate enforcement** (~2–4 days) — permanently eliminates the bypass class; makes trust_level/scheduler flags real; enables the effective-policy viewer later.
3. **Lock/slot race fixes** (~1 day) — restore ADR-041 and KV integrity.
4. **Streaming honesty pair** (~1 day) — end "silent truncation" era.
5. **Workflow lifecycle milestone** (~1 week) — RUNNING rows, cancellation ceiling, self-trigger refusal, cron-as-real-schedules, test isolation: transforms the weakest subsystem into a trustworthy automation surface and unlocks the product roadmap (durable executions, simulation mode, NL authoring).
6. **Telegram concurrent updates** (XS, after lock fix) — biggest perceived-latency win in daily use.
7. **Delta tokenization cache** — largest recurring hot-path compute/network saving.

## Top five recommendations

1. **Fix the ground truth first**: gates green + CI blocking, then land SEC-001's chokepoint refactor with its regression test. Nothing else is reliably verifiable until this holds.
2. **Restore the concurrency invariants** (session lock, slot eviction) before adding Telegram concurrency — correctness first, then throughput.
3. **Treat workflows as v1, not done**: adopt the turn-journal pattern (execution rows created upfront, node results appended) plus trigger-registration fixes. This is incremental — patterns exist in-repo — not a rewrite.
4. **Adopt a loud-failure convention**: every silent path found here becomes actionable feedback (interpolation warnings, skipped-node results, truncation markers). Cheap individually; compounding culturally.
5. **Ship the stranded small stuff**: Defer button exists backend-only; voice confirmation parity; contrast tokens; routing. These are days of work buying disproportionate user trust.

## Recommended order of work

**Immediate:** gates+CI → gate chokepoint → session-lock fix → memory fail-closed → login bundle → slot locking → streaming honesty → persistence quick fixes → frontend work-loss pair → scheduler backoff. *(≈ 2 focused loops)*
**Short term:** SQLite pragmas/index/retention → Telegram concurrency → workflow lifecycle milestone + test isolation → context-window selector fixes → maintenance robustness batch → voice/confirmation fixes → browser SSRF completion → platform contract extraction → bundle split. *(≈ 4–6 loops)*
**Medium term:** workflow timeline/cancellation UI → delta tokenization → effective-policy viewer → editor learnability → terminal/file hardening → a11y bundle → delete-list.
**Long term:** the Action Registry → activity journal → durable executions → simulation arc (`13_IDEAS_AND_FUTURE_DIRECTIONS.md`).

---

*One-sentence verdict:* Hestia's foundations are sound enough that fixing its two Critical holes, restoring its gates, and finishing the workflow engine would move it from "impressive solo project with sharp edges" to "trustworthy personal infrastructure" without rewriting anything that matters.
