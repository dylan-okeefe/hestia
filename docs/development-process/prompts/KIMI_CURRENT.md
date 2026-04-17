# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-17 (L21 queued — context resilience + handoff summaries + Hermes untangle docs)

---

## Current task

**Active loop:** **L21** — Context resilience: session handoff summaries,
history compressor, loud overflow signal, platform warning channel, and
documentation to untangle Hestia's runtime from the Hermes llama-server.

**Spec:** [`../kimi-loops/L21-context-resilience-handoff-summaries.md`](../kimi-loops/L21-context-resilience-handoff-summaries.md)

**Branch:** `feature/l21-context-resilience-handoff` (already created from `develop`).

**Kimi prompt:** Read this file, then execute the full spec at the linked
file. Implement every section §-1 through §9 in order. §6 is docs-only
(coexistence with Hermes llama-server). All other sections touch source
code under `src/hestia/` plus new tests. Commit one section per commit as
the spec directs. Stop and report immediately if any section fails. Write
the `.kimi-done` artifact at the end (do not commit it).

**Scope (summary, see spec for detail):**

- `src/hestia/memory/handoff.py` — `SessionHandoffSummarizer` (§1)
- `src/hestia/context/compressor.py` — `HistoryCompressor` protocol +
  `InferenceHistoryCompressor` default (§2)
- `src/hestia/context/builder.py` — raise `ContextTooLargeError` on
  protected-block overflow; thread compressor through `build()` (§2, §3)
- `src/hestia/orchestrator/engine.py` — catch `ContextTooLargeError`,
  record failure, kick handoff summarizer, call
  `platform.send_system_warning` (§3)
- `src/hestia/config.py` — `HandoffConfig`, `CompressionConfig`, wired
  through `TrustConfig` presets (§4)
- `src/hestia/platforms/{base,cli_adapter,telegram_adapter,matrix_adapter}.py`
  — `send_system_warning` abstract + implementations (§5)
- `deploy/hestia-llama.alt-port.service.example`, updated
  `deploy/README.md`, new `docs/guides/runtime-setup.md`,
  ADR-0015 llama-server coexistence (§6)
- `README.md` context-budget section, `docs/runtime-feature-testing.md`
  update, ADR-0014 context-resilience (§7)
- Version bump to **0.4.0**, changelog under `## [0.4.0]`, `uv.lock`
  regenerated in the same commit (§8)
- Handoff report `docs/handoffs/L21-context-resilience-handoff.md` (§9)

**Do not merge to `develop` in this loop.** Push the feature branch and
stop after `.kimi-done`.

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- Context-overflow analysis (primary motivation):
  [`../reviews/context-overflow-analysis-april-17.md`](../reviews/context-overflow-analysis-april-17.md)
- Capability audit (trust context for §4):
  [`../reviews/capability-audit-april-17.md`](../reviews/capability-audit-april-17.md)

---

## `.kimi-done` contract (mandatory, see `.cursorrules`)

At successful completion, write `./.kimi-done` with at minimum:

```
HESTIA_KIMI_DONE=1
LOOP=L21
BRANCH=feature/l21-context-resilience-handoff
COMMIT=<final commit sha>
TESTS=<pytest summary line, e.g. "passed=N failed=0 skipped=M">
```

If blocked (auth failure, script error, spec impossible), still write
`.kimi-done` with `HESTIA_KIMI_DONE=0` and a `BLOCKER=<reason>` line.
