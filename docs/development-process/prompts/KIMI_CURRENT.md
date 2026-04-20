# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-20 (L45 multi-user safety train complete;
awaiting release-train merge sequencing)

---

## Current task

**Status:** **IDLE** — L45a, L45b, and L45c all complete on their feature
branches. L43 voice-calls remains blocked on Dylan-side prerequisites.

---

## L45 multi-user safety train — completion snapshot

Scope doc: [`v0.8.x-multi-user-safety-release-prep.md`](v0.8.x-multi-user-safety-release-prep.md)

### L45a — Trust + identity plumbing

- Branch: `feature/l45a-trust-identity-plumbing` (pushed to
  `origin/feature/l45a-trust-identity-plumbing`)
- Implementation commit: `281ae90`
- Import sort fix: `80d3724`
- Orchestration commit: `4203fb9`
- Tests: **805 passed, 6 skipped**
- mypy: **0 errors (92 files)**
- ruff: **23 errors (baseline)**
- Merge status: **NOT merged to `develop`** (awaits release-train sequencing)

### L45b — Memory user-scope migration

- Branch: `feature/l45b-memory-user-scope-migration` (pushed to
  `origin/feature/l45b-memory-user-scope-migration`)
- Base: `feature/l45a-trust-identity-plumbing` (proper chain)
- Implementation commit: `6ea59ed`
- Orchestration commit: `31533b3`
- Tests: **820 passed, 6 skipped**
- mypy: **0 errors (92 files)**
- ruff: **23 errors (baseline)**
- Merge status: **NOT merged to `develop`** (awaits release-train sequencing)

### L45c — Multi-user docs + allow-list hardening

- Branch: `feature/l45c-multi-user-docs-and-hardening` (pushed to
  `origin/feature/l45c-multi-user-docs-and-hardening`)
- Base: **develop (`df8a501`) — Kimi branched from develop instead of from
  L45b**. Content (allow-list + docs) is orthogonal to L45a/L45b, so this is
  functionally fine but the chain is technically broken. Release-train merge
  sequence below handles this correctly.
- Implementation commit: `de231f2`
- Orchestration commit: `f3e8013`
- Tests: **818 passed, 6 skipped**
- mypy: **0 errors (93 files)**
- ruff: **23 errors (baseline)**
- Merge status: **NOT merged to `develop`** (awaits release-train sequencing)

---

## Release-train merge sequence (when ready)

The v0.8.x multi-user safety release scope (see scope doc) includes:

1. `feature/l40-copilot-cleanup`
2. `feature/voice-shared-infra`
3. `feature/voice-phase-a-messages`
4. `feature/l45a-trust-identity-plumbing`
5. `feature/l45b-memory-user-scope-migration`
6. `feature/l45c-multi-user-docs-and-hardening`

`feature/voice-phase-b-calls` is explicitly out of scope (blocked on Dylan-side
prereqs). Merge order above preserves dependencies. L45c does not depend on
L45b code-wise, so merging it after L45b will succeed cleanly.

After all six branches are on `develop` and gates are green, tag a release
(version name TBD based on scope) and merge `develop` to `main`.

---

## Post-release policy state

The `.cursorrules` "Post-release merge discipline" rule remains in effect for
all branches above. Planning-doc updates (this file, loop log, kimi-phase-queue,
scope doc, loop specs, handoffs, ADRs) are the explicit exception.

---

## Existing blocked work (unchanged)

- **L43 voice calls** remains blocked on Dylan-side prerequisites (dedicated
  phone number, Telegram API app, `py-tgcalls` readiness, Piper voice files).

---

## Deferred (pre-existing backlog)

- **L39** — `hestia upgrade` command (auto-fix `hestia doctor` findings).
- **L44** — Dogfooding journal rollup after a week of real v0.8.0 use.

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- Multi-user release scope: [`v0.8.x-multi-user-safety-release-prep.md`](v0.8.x-multi-user-safety-release-prep.md)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md)
- Post-release merge discipline: `.cursorrules`
