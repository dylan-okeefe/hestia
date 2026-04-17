# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-17 (L20 queued — TrustConfig + web_search)

---

## Current task

**Active loop:** **L20** — Trust profile config + Web search tool (feature loop, no release/merge-to-main in this loop).

**Spec:** [`../kimi-loops/L20-trust-config-and-web-search.md`](../kimi-loops/L20-trust-config-and-web-search.md)

**Branch:** `feature/l20-trust-config-and-web-search` (create from `develop`).

**Kimi prompt:** Read this file, then execute the full spec at the linked file. Implement every section §-1 through §11 in order. Stop and report immediately if any section fails. Write the `.kimi-done` artifact at the end (do not commit it).

**Scope:**
- Add `TrustConfig` with presets (`paranoid`, `household`, `developer`) and wire it through policy/orchestrator/CLI
- Add `WebSearchConfig` and `web_search` builtin (Tavily provider), conditionally registered only when configured
- Add/extend tests for trust policy gating, confirmation auto-approve behavior, and web search tool behavior
- Update docs and changelog `[Unreleased]`, bump version to `0.3.0`
- Final verification and push **feature branch only** (do not merge to `develop` in this loop)

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md)
- Kimi script: [`../../../scripts/kimi-run-current.sh`](../../../scripts/kimi-run-current.sh)
