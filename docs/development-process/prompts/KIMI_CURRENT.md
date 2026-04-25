# Kimi — current task (orchestration pointer)

**Orchestrator:** Kimi (self-orchestrating via subagents)

**Last set by:** Kimi — 2026-04-25 (L55 merged to develop)

---

## Current task

**Status:** **ACTIVE — L56 queued.**

The v0.10.0 pre-release evaluation identified ~15 bugs, architecture seams,
and polish items. Organized into a 6-loop arc (L54–L59).

**L54 and L55** are complete and merged to `develop`.
**L56–L59** are v0.11 feature-branch work (do not merge to develop until
release-prep).

### Recently completed (merged to develop):
- **L54** — Async safety & small bugs (9 commits, 10 sections)
- **L55** — Code cleanup & release prep (5 commits, 5 sections)
- **L53 (ad-hoc)** — Tavily integration, Telegram HTML markdown, DuckDuckGo
  fallback, conversation audit guide.

---

## Active loop: L56 — Orchestrator Decomposition

**Branch:** `feature/l56-orchestrator-decomposition`  
**Spec:** [`kimi-loops/L56-orchestrator-decomposition.md`](kimi-loops/L56-orchestrator-decomposition.md)  
**Merge target:** release-prep (do NOT merge to develop until v0.11 release-prep)

**Scope summary:**
Decompose `orchestrator/engine.py` (982 lines, 15+ concerns) into three phases:
1. **TurnAssembly** — context building, style prefix, voice prompt, slot acquisition
2. **TurnExecution** — inference loop, tool dispatch, confirmation gating, injection scanning
3. **TurnFinalization** — trace recording, failure bundles, slot save, handoff summary

**Quality gates:** `pytest`, `mypy`, `ruff` — all green.

---

## Queue (next up)

| Loop | Branch | Spec | Merge target |
|------|--------|------|--------------|
| L57 | `feature/l57-app-bootstrap-cleanup` | [`kimi-loops/L57-app-bootstrap-cleanup.md`](kimi-loops/L57-app-bootstrap-cleanup.md) | release-prep |
| L58 | `feature/l58-config-and-ux-polish` | [`kimi-loops/L58-config-and-ux-polish.md`](kimi-loops/L58-config-and-ux-polish.md) | release-prep |
| L59 | `feature/l59-security-docs-and-infrastructure` | [`kimi-loops/L59-security-docs-and-infrastructure.md`](kimi-loops/L59-security-docs-and-infrastructure.md) | release-prep |

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
