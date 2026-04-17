# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-17 (**L19 queued — slot-save fix + ctx-window alignment + v0.2.2**)

---

## Current task

**Active loop:** **L19** — slot-save basename fix + ctx-window policy alignment + KV-cache docs consistency → v0.2.2

**Spec:** [`../kimi-loops/L19-slot-save-and-ctx-alignment-v0.2.2.md`](../kimi-loops/L19-slot-save-and-ctx-alignment-v0.2.2.md)

**Branch:** `feature/l19-slot-save-and-ctx-alignment` (create from `develop`).

**Kimi prompt:** Read this file, then execute the full spec at the linked file. Implement every section §1–§7 in order. Stop and report immediately if any section fails. Write the `.kimi-done` artifact at the end (do not commit it).

**Scope:**
- §1 Slot-save/restore: pass basename instead of absolute path; migration for legacy DB values; tests
- §2 Wire `DefaultPolicyEngine.ctx_window` from new `InferenceConfig.context_length` field; correct per-slot default
- §3 Fix README KV-cache quant example (`q4_0` → `turbo3`) to match deploy
- §4 Optional: align `deploy/hestia-llama.service` ExecStart with the new defaults
- §5 CHANGELOG + version bump to 0.2.2
- §6 Promote `develop` → `main`, tag v0.2.2, push
- §7 Branch cleanup + final verification

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md)
- Kimi script: [`../../../scripts/kimi-run-current.sh`](../../../scripts/kimi-run-current.sh)
