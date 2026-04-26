# Kimi — current task (orchestration pointer)

**Orchestrator:** Kimi (self-orchestrating via subagents)

**Last set by:** Kimi — 2026-04-25 (L58 complete)

---

## Current task

**Status:** **ACTIVE — L59 queued.**

The v0.10.0 pre-release evaluation identified ~15 bugs, architecture seams,
and polish items. Organized into a 6-loop arc (L54–L59).

**L54, L55, L56, L57, and L58** are complete.
L54–L55 are merged to `develop`.
L56–L58 are feature-branch work (do not merge to develop until release-prep).

---

## Active loop: L59 — Security Docs & Infrastructure

**Branch:** `feature/l59-security-docs-and-infrastructure`  
**Spec:** [`kimi-loops/L59-security-docs-and-infrastructure.md`](kimi-loops/L59-security-docs-and-infrastructure.md)  
**Merge target:** release-prep (do NOT merge to develop until v0.11 release-prep)

**Scope summary:**
1. **§1** — Document injection scanner behavior (annotate-not-block design)
2. **§2** — Telegram allowed_users hard error (raise ValueError at startup)
3. **§3** — Memory table alembic migration (move schema evolution to alembic)
4. **§4** — Skills feature assessment (readiness check, doctor integration)

**Quality gates:** `pytest`, `mypy`, `ruff` — all green.

---

## Queue (completed)

| Loop | Branch | Status |
|------|--------|--------|
| L54 | `feature/l54-async-safety-and-small-bugs` | Merged to `develop` |
| L55 | `feature/l55-code-cleanup-release-prep` | Merged to `develop` |
| L56 | `feature/l56-orchestrator-decomposition` | Complete, on branch |
| L57 | `feature/l57-app-bootstrap-cleanup` | Complete, on branch |
| L58 | `feature/l58-config-and-ux-polish` | Complete, on branch |

---

## What's queued (not authorized yet)

### Voice Phase B (Discord) → v0.11+ candidate
- Specified in `v0.8.0-release-and-voice-launch.md` Track 5 Phase B.
- **Blocked on Dylan-side prereqs** (Discord token, guild/channel IDs, etc.).

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md)
- Release discipline: `.cursorrules`
