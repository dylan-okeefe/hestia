# Kimi — current task (orchestration pointer)

**Orchestrator:** Kimi (self-orchestrating via subagents)

**Last set by:** Kimi — 2026-04-25 (v0.10.0 pre-release evaluation processed)

---

## Current task

**Status:** **ACTIVE — L54 in progress.**

The v0.10.0 pre-release evaluation identified ~15 bugs, architecture seams,
and polish items. These have been organized into a 6-loop arc (L54–L59).

**L54 and L55** are pre-release hotfixes that merge directly to `develop`.
**L56–L59** are v0.11 feature-branch work.

### Recently completed (merged to develop):
- **L47–L52** — ADR normalization, config consistency, orchestrator extract,
  commands split, test coverage, ContextBuilder decomposition.
- **L53 (ad-hoc)** — Tavily integration, Telegram HTML markdown, DuckDuckGo
  fallback, conversation audit guide.

---

## Active loop: L55 — Code Cleanup & Release Prep

**Branch:** `feature/l55-code-cleanup-release-prep`  
**Spec:** [`kimi-loops/L55-code-cleanup-release-prep.md`](kimi-loops/L55-code-cleanup-release-prep.md)  
**Merge target:** `develop`

**Scope summary:**
1. Strip internal review-tracking comments (`# Copilot H-X`, `# M-X`, etc.)
2. `TurnContext.session` should be non-optional
3. `SkillIndexBuilder` divergence — one canonical format method
4. Tool factory return type cleanup (remove `cast()`)
5. Meta-command handler relocation to `commands/meta.py`

**Quality gates:** `pytest`, `mypy`, `ruff` — all green before merge.

---

## Queue (next up)

| Loop | Branch | Spec | Merge target |
|------|--------|------|--------------|
| L56 | `feature/l56-orchestrator-decomposition` | [`kimi-loops/L56-orchestrator-decomposition.md`](kimi-loops/L56-orchestrator-decomposition.md) | release-prep |
| L57 | `feature/l57-app-bootstrap-cleanup` | [`kimi-loops/L57-app-bootstrap-cleanup.md`](kimi-loops/L57-app-bootstrap-cleanup.md) | release-prep |
| L58 | `feature/l58-config-and-ux-polish` | [`kimi-loops/L58-config-and-ux-polish.md`](kimi-loops/L58-config-and-ux-polish.md) | release-prep |
| L59 | `feature/l59-security-docs-and-infrastructure` | [`kimi-loops/L59-security-docs-and-infrastructure.md`](kimi-loops/L59-security-docs-and-infrastructure.md) | release-prep |

---

## What's queued (not authorized yet)

### Voice Phase B (Discord) → v0.11+ candidate
- Specified in `v0.8.0-release-and-voice-launch.md` Track 5 Phase B.
- **Blocked on Dylan-side prereqs** (Discord token, guild/channel IDs, etc.).

### Deferred (pre-existing backlog)
- **L39** — `hestia upgrade` command.
- **L44** — Dogfooding journal rollup.

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md)
- Release discipline: `.cursorrules`
