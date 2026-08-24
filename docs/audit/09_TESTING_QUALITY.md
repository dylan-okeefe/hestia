# Testing & Quality Engineering Audit — Hestia

**Audit date:** 2026-08-22 · Scope: `tests/` architecture, gate health, invariant coverage, gaps.
All numbers below are from runs executed during this audit.

---

## 1. Gate health (measured)

| Gate | Result | Detail |
|------|--------|--------|
| pytest unit+integration | ✅ **2272 passed / 6 skipped**, ~260 s, identical across 4 consecutive runs (deterministic) | no flakes observed |
| mypy `src/hestia` | ❌ **7 errors** | `voice/pipeline.py` optional-dependency guards; `stealth.py` import-untyped override |
| ruff `src/ tests/` | ❌ **49 errors** (27 auto-fixable) | missing `Any` imports etc.; baseline drifted |
| web-ui build | ❌ **broken** (`TS2339` in `useWorkflowEditor.ts:160`) | see BUG-049 |

The project's own docs treat these as blocking gates ("all three must pass before advancing"). All three colored gates are currently red on the runtime branch — evidence that gates stopped being enforced recently (consistent with git history showing the last merges salvaged from runtime sessions). **Restoring green and wiring all four into CI is itself a high-leverage fix**: it converts every finding in this audit's register from "reviewer vigilance" to "merge blocker."

## 2. Test architecture

```
tests/
  unit/           # majority; real async SQLite, fakes at true boundaries
  integration/    # orchestrator flows, egress audit, platform adapters
  docs/           # validates README links/content, SECURITY.md, UPGRADE claims
```

- **Mocking altitude is correct throughout**: fakes sit at genuine boundaries (inference client, IMAP socket, HTTP via respx, Playwright) while registries, stores, gates, and orchestrators run as real code over real async SQLite. Zero self-mocking of modules-under-test detected; zero assertion-free tests.
- **Concurrency testing is real, not theater**: 20-writer `asyncio.gather` races with exact post-state assertions (`test_append_message_race.py`, `test_sessions_race.py`), event-handshake coordination for slot concurrency, IMAP command non-interleaving.
- **Decision traceability**: test docstrings cite audit IDs and ADRs ("Copilot audit C-2", "H-5", "L222 §4"), explaining which historical regression each pins.
- Slowest single test ≈1.5 s; sleeps patched or ≤50 ms except five deliberate adapter rate-limit tests. E2E against real Matrix/Synapse exists but env-gated with graceful skips.

This is a genuinely high-quality test *architecture*; its risks are process drift (red gates) and specific blind spots, not design weakness.

## 3. Invariant coverage (ADR promises vs regressions)

| Critical invariant | Dedicated tests? | Evidence |
|---|---|---|
| SSRF blocking (ADR-045) | ✅ deepest in repo | pre-flight + transport-level blocks (loopback/RFC1918/CGNAT/metadata), DNS-rebinding via patched getaddrinfo, redirect-to-metadata via mock inner transport, curl_cffi IPv6 loopback, browser pre-launch refusal |
| Injection-flagged escalation (ADR-043) | ✅ three layers | gate deny/escalate per channel + subagent always-deny (`policy/test_gate.py:198-285`); orchestrator flags from history (`test_execution_gate.py:327`); scanner pattern/entropy/false-positive suites |
| Confirmation requester binding (L222§4/ADR-012/034) | ✅ store+adapter+orchestrator | wrong-user approval rejected; Telegram button press by user 99999 rejected vs requester 12345 |
| Per-session serialization (ADR-041) | ⚠️ partial | race tests cover append/get-or-create; **no test exercises lock pruning with pending waiters** — precisely where BUG-001 lives |
| Migration idempotency | ⚠️ partial | users-migration idempotency tested; **Alembic has zero replay/downgrade harness**; runtime-migration re-run covered implicitly only |
| Slot lifecycle under eviction races (ADR-013) | ⚠️ partial | slow-erase-doesn't-stall-acquire tested; **evict-vs-acquire interleaving untested** (BUG-002 territory) |
| Workflow trust gating (ADR-042 as applied to nodes) | ❌ absent | no test asserts a workflow tool_call node is denied anything — consistent with SEC-001 having gone unnoticed |

## 4. Coverage gaps (module → status)

Thin or absent, ranked by risk:

1. **Workflows executor security path** — nothing asserts gating on any node type (SEC-001).
2. **`rollback_turn` tool** — no tests at all despite destructive file operations.
3. **Scheduler tool wrappers** incl. `_verify_task_ownership` (`scheduler_tools.py:31`) — security-adjacent ownership check untested.
4. **Voice pipeline** — thin; STT/TTS fallback paths largely uncovered.
5. **Web routes** — auth thoroughly tested; several route modules partially (memory topics IDOR paths would have been caught).
6. **Browser stream manager** — lifecycle/timeout paths lightly covered.
7. **Frontend unit coverage** exists (11 page suites + 23 Playwright specs) but the broken build proves typecheck/build isn't gated in practice.

## 5. Brittleness & hygiene findings

| ID | Finding | Detail |
|----|---------|--------|
| TEST-001 | Red gates normalized | 49 ruff + 7 mypy errors on branch; build broken — gates exist on paper, not in enforcement |
| TEST-002 | No `pytest-timeout` | a hung test hangs CI indefinitely; config investment (markers, filterwarnings) shows intent to gate but timeout missing |
| TEST-003 | Fixture duplication between trees | `db` fixture + fakes re-declared in unit and integration conftest — drift risk (the two copies of the IN-clause bug pattern rhyme with this) |
| TEST-004 | Handoff-flow teardown warning | aiosqlite connection closed after loop teardown → PytestUnhandledThreadExceptionWarning not yet escalated to error |
| TEST-005 | Dead markers | `anyio` markers registered/unused; explicit asyncio marks redundant on modern config |
| TEST-006 | Weak test present | `test_auth_disabled_allows_all` asserts little; strengthen or delete |
| TEST-007 | Alembic zero coverage | no upgrade→downgrade→replay harness anywhere; schema.py drift already proven (F8/F9 in persistence doc) |
| TEST-008 | Missing interleaving tests | BUG-001/BUG-002 both live in interleavings the suite never constructs (waiter-present prune; evict-vs-acquire). The suite's own race-testing style would catch both cheaply |

## 6. Important missing integration/E2E scenarios

1. **Two concurrent messages to one session while first turn holds lock** (would catch BUG-001 deterministically).
2. **Workflow webhook → tool_call node → paranoid preset** end-to-end denial (SEC-001).
3. **llama-server connection drop mid-stream** → user-visible outcome assertions (currently the asymmetry BUG-003/022 ships unnoticed).
4. **Nightly maintenance against adversarial memory content** (FTS5 metacharacters — BUG-011).
5. **Session-expiry mid-edit in dashboard** preserving drafts (BUG-055).
6. **Multi-platform serve shutdown isolation** — one adapter crashing must not kill siblings (BUG-013).

## 7. Recommendations (priority order)

1. **Restore green gates + wire CI** (ruff --fix for 27; hand-fix rest; fix TS error; add web-ui build + mypy + ruff to CI as blocking). Highest leverage-per-effort in this entire document.
2. Add `pytest-timeout = 120` and escalate the teardown warning once fixed.
3. Consolidate fixtures into one shared module importable by both trees.
4. Write the six missing integration scenarios above (the existing fake infrastructure supports all of them without new machinery).
5. Add interleaving unit tests for lock-prune-with-waiters and slot evict-vs-acquire before fixing those bugs (test-first per house style).
6. Delete dead markers; strengthen/delete TEST-006.
