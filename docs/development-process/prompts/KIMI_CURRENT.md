# Kimi — current task (orchestration pointer)

**Orchestrator:** Kimi (self-orchestrating via subagents)

**Last set by:** Kimi — 2026-04-25 (L57 complete on feature branch)

---

## Current task

**Status:** **ACTIVE — L58 in progress.**

**L54 and L55** are merged to `develop`.
**L56 and L57** are complete on feature branches (do not merge until v0.11 release-prep).

### Recently completed:
- **L57** — App bootstrap cleanup (3 commits, scheduler helpers, memory epoch relocation, CliAppContext simplification)
- **L56** — Orchestrator decomposition (4 commits, engine.py 978→284 lines)
- **L55** — Code cleanup & release prep (5 commits, merged to develop)
- **L54** — Async safety & small bugs (9 commits, merged to develop)

---

## Active loop: L58 — Config, UX & Timezone Polish

**Branch:** `feature/l58-config-and-ux-polish`  
**Spec:** [`kimi-loops/L58-config-and-ux-polish.md`](kimi-loops/L58-config-and-ux-polish.md)  
**Merge target:** release-prep (do NOT merge to develop until v0.11 release-prep)

**Scope summary:**
1. Split `_ConfigFromEnv` into `config_env.py`
2. Timezone suffix on all displayed timestamps
3. Token usage visibility in chat
4. `/status` in REPL
5. `hestia ask` vs `hestia chat` clarity
6. Schedule list format improvements

---

## Queue (next up)

| Loop | Branch | Spec | Merge target |
|------|--------|------|--------------|
| L59 | `feature/l59-security-docs-and-infrastructure` | [`kimi-loops/L59-security-docs-and-infrastructure.md`](kimi-loops/L59-security-docs-and-infrastructure.md) | release-prep |

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md)
- Release discipline: `.cursorrules`
