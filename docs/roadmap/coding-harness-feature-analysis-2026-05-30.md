# Coding-Harness Feature Analysis — little-coder & smallcode → Hestia

**Date:** 2026-05-30
**Sources:** local clones in `.harness-research/` (`little-coder`, `smallcode`)
**Question:** which small-model coding-harness features are worth pulling into Hestia,
given a Qwen 3.6 35B-A3B MoE at ~40 tok/s / 131k context on the new box (Ryzen 7 3700X,
48 GB RAM, RTX 3060 12GB).

---

## 0. The one data point that should anchor everything

`little-coder/docs/benchmark-qwen3.6-35b-a3b.md` is a full 225-exercise Aider Polyglot
run on **the exact model you're now running**:

```
Qwen3.6-35B-A3B + little-coder harness:  177/225 = 78.7%
Qwen3.5 9B   + same harness:             ~45%
vanilla Aider + Qwen3.5 9B (ablation):   43/225 = 19.1%
```

Two takeaways:

1. **The harness is worth ~25 pp on its own** (vanilla Aider 19% vs little-coder 45% on the
   *same 9B model*). The scaffolding is not decoration; it's most of the score on small models.
2. **The 35B-A3B jump was almost entirely first-attempt passes** (37.6% → 70.2% first-attempt;
   retry rate barely moved). Translation: with your new model, the model is now *capable*
   enough that good harness ergonomics convert directly into solved tasks. Coding on Hestia is
   genuinely reasonable now — this is not wishful thinking.

So: yes, build toward coding. But the highest-leverage work is **harness mechanics that also
make the everyday assistant more reliable**, because Hestia is an assistant first.

**Evidence-quality caveat:** little-coder's benchmark is rigorous and reproducible (real Aider
Polyglot, vanilla-Aider ablation baseline, two reproduction runs). smallcode's `COMPARISON.md`
numbers are self-reported with "estimated" competitor scores — treat smallcode as an **idea
mine**, not a benchmark authority. Also note smallcode's `src/compiled/` is partly hand-written
JS despite the "compiled from MarrowScript" headers (their own ARCHITECTURE.md admits this), so
it's a source of *designs*, not drop-in code.

---

## 1. What Hestia already has (don't rebuild these)

Hestia is further along than either harness on several axes. Mapping the overlap so we don't
duplicate:

| Harness feature | Hestia equivalent | Status |
|---|---|---|
| turn cap | `max_iterations=10` in `orchestrator/execution.py` | ✅ have |
| thinking/reasoning budget | `policy.reasoning_budget()` passed to llama | ⚠️ partial (see T1.3) |
| text/XML tool-call fallback | `_extract_tool_calls_from_text()` | ⚠️ XML-only (see T1.2) |
| loop / empty-arg circuit breaker | circuit breaker in `execution.py:481` | ⚠️ partial (see T1.4) |
| reasoning-without-action nudge | guard in `execution.py:119` | ✅ have |
| prompt-injection scan | `security/injection.py` | ✅ have (stronger than theirs) |
| SSRF guard | `SSRFSafeTransport` | ✅ have |
| token budgeting + compaction | `context/builder.py` + compressor | ✅ have (with C1 caching bug — see other review) |
| persistent memory FTS5 | `memory/store.py` SQLite FTS5 | ✅ identical approach to smallcode |
| permission/trust gating | `policy/` + trust presets | ✅ have (richer than theirs) |
| tool-output truncation | artifact promotion + `max_inline_chars` | ✅ have |
| same-process subagents | `delegate_task` + slot manager | ✅ have |
| traces / failure bundles | `trace_store`, `failure_store` | ✅ have |
| per-model profiles | partial — config is per-deployment | ⚠️ partial (see T2.4) |

The gaps are concentrated in **code-editing primitives** and **a few harness-robustness
upgrades**. That's the whole opportunity.

---

## 2. TIER 1 — Make a ton of sense (high leverage, fits the architecture)

These are ordered by value-per-effort.

### T1.1 — A surgical `edit_file` (str-replace) tool + Write-guard. **[biggest single win]**
- **What:** Both harnesses make *patch / edit* the primary write primitive, not whole-file
  write. little-coder additionally makes `Write` **refuse on an existing file** and return the
  exact `Edit` call-shape to use instead (`write-guard/index.ts`). Their note: this guard fires
  on ~57% of Polyglot exercises and is load-bearing for the benchmark score.
- **Why it matters here:** Hestia today has `write_file` and `append_to_file` but **no surgical
  edit**. Small/quantized models truncate, drop imports, and drift indentation when asked to
  reproduce a whole file. A 10-line str-replace is dramatically more reliable *and* cheaper on
  context — which is the entire constraint envelope.
- **Hestia fit:** New builtin `edit_file(path, old_string, new_string)` mirroring Cursor's
  StrReplace semantics (old_string must match exactly once; include surrounding context). Add a
  policy/tool-level guard: `write_file` on an existing path returns a structured "use edit_file"
  error instead of overwriting. Plays directly with the existing `requires_confirmation` +
  trust flow.
- **Effort:** Small-to-medium. One new tool + one guard. High confidence.

### T1.2 — Upgrade the tool-call fallback to a full JSON repairer.
- **What:** little-coder's `output-parser/parser.ts` `repairJson()` handles, in order: literal
  newlines/tabs in strings, trailing commas, single→double quotes, unquoted keys, missing
  closing braces/brackets, and "extract first JSON object." Plus extraction from ```` ```json ````
  fences, `<tool_call>` tags, and bare `{"name":...}` objects.
- **Why it matters here:** Hestia's `_extract_tool_calls_from_text()` only catches XML-style
  `<tool_call>` tags. On quantized models, malformed-but-recoverable JSON (trailing comma,
  fenced block) is common and currently turns into a wasted turn. This is the cheapest way to
  recover real wall-clock time on every coding turn.
- **Hestia fit:** Extend `core/inference.py` parsing (and the streaming accumulator in
  `execution.py`) with a `repair_json` pass before giving up. Pairs with the streaming-vs-
  non-streaming consistency fix already flagged in the v0.12 review (M1).
- **Effort:** Small. Pure function + tests. Very high confidence.

### T1.3 — Mid-stream thinking-budget abort + "commit now" nudge.
- **What:** little-coder's `thinking-budget/index.ts` counts thinking-delta tokens *during the
  stream*, and on breach: disables thinking, queues a "stop deliberating, use your tools" follow-
  up, and aborts the over-long turn (re-asserting thinking-off across the restart). Their headline
  failure mode (`bowling`, failed in all languages) is exactly "model burns the turn budget
  deliberating and never converges."
- **Why it matters here:** Hestia already passes a `reasoning_budget` to llama and has a
  *post-hoc* "you reasoned a lot, emit a tool call" nudge — but only *after* a full response
  comes back. On a slow local model, runaway reasoning is the single biggest wall-clock waster.
  Aborting mid-stream reclaims minutes per stuck turn.
- **Hestia fit:** Hestia already streams (`chat_stream` / `_run_inference_streaming`). Add a
  thinking-token counter in the stream loop that, on breach, cancels the stream and re-prompts
  with a commit instruction. The state machine already supports `RETRYING`.
- **Effort:** Medium (touches the streaming path + transition logic). High value.

### T1.4 — Promote the circuit breaker into a full quality-monitor with targeted corrections.
- **What:** little-coder `quality-monitor/quality.ts` + smallcode `governor/early_stop.js`
  classify degenerate output and inject a *specific* correction:
  - empty response → "respond with text or a tool call"
  - hallucinated tool name → "that tool doesn't exist; valid tools are X, Y, Z"
  - repeated identical tool call → "you're looping; try a different approach"
  - patch failed N times on a file → "stop patching; read it and rewrite from scratch"
  - read-only-tool streak (≥5/≥8) with no output → "you have enough context; write your answer"
  - greeting mid-task → "you lost context; continue where you left off, don't restart"
- **Why it matters here:** Hestia has a circuit breaker only for repeated *empty-arg* failures.
  The above taxonomy covers the other common small-model failure modes with cheap, deterministic
  detection and a tailored re-prompt — each one saves a turn instead of failing the turn.
- **Hestia fit:** A small `quality.py` consulted in the execution loop; corrections fed back as
  the next user/system nudge. The "hallucinated tool" correction should list the *session's*
  allowed tools (Hestia already computes `allowed_tools`).
- **Effort:** Medium. Mostly net-new but self-contained.

### T1.5 — Dedicated `glob` and `grep` tools (code search) + per-turn file checkpoint.
- **What:** Both harnesses give the model first-class `Glob`/`Grep` and snapshot files before
  any mutating op (`checkpoint/` in little-coder, `snapshot.js`/`undo.js` in smallcode) so a turn
  can be rewound; smallcode auto-rolls-back a turn's edits if validation hard-fails.
- **Why it matters here:** For coding, "search by name / search by content" as explicit tools
  beats making the model construct `find`/`rg` shell strings (small models botch the flags). And
  edit safety net: a bad multi-file edit on a real repo is destructive; a per-turn checkpoint
  makes the agent safe to run unattended (which is your overnight-Kimi use case generalized).
- **Hestia fit:** `glob`/`grep` are thin wrappers over ripgrep with output truncation (reuse the
  artifact path). Checkpoint = a lightweight git-stash or copy-on-write snapshot keyed to the
  turn id, wired into `finalization.py`. Hestia already has the turn lifecycle to hang this on.
- **Effort:** glob/grep small; checkpoint medium. Do glob/grep first.

---

## 3. TIER 2 — Might be helpful (real value, but conditional or heavier)

### T2.1 — Plan-tracker with a re-injected "ACTIVE PLAN" anchor.
- **What:** smallcode's single biggest multi-file reliability claim: for multi-step tasks, force
  a numbered plan up front, then re-inject it every turn with a `→ step 3 of 5` cursor that
  advances as the model reports progress (`session/plan_tracker.js`).
- **Why conditional:** Hestia already has a `TodoWrite`-style concept and memory epochs; the
  *anchor re-injection* is the novel part. It's a real win for long coding tasks but costs tokens
  every turn and needs the model to emit progress markers. Worth it once coding tasks routinely
  exceed ~4 steps; overkill for assistant chat.
- **Effort:** Medium.

### T2.2 — LSP / diagnostics feedback loop (compile/lint after edit).
- **What:** little-coder has `GetDiagnostics`; smallcode runs compile/lint after every write and
  feeds errors back (`git/lsp_validate.ms`, `src/lsp/client.js`), plus a test-runner with
  structured output for a TDD loop.
- **Why conditional:** Enormous quality lever for coding (the model fixes its own type/lint
  errors before claiming done), but it's the heaviest item: per-language toolchain wiring, an LSP
  client, and a test-runner tool. Only pays off once coding is a committed, recurring use case.
  For Hestia today, a lean first version = a `run_tests`/`lint` tool the model calls explicitly,
  not a full LSP integration.
- **Effort:** Large (LSP) / Medium (just a test-runner tool).

### T2.3 — Read-result trim-on-overflow guard.
- **What:** little-coder `read-guard/index.ts`: if a read result would push context past the
  window, replace it with the first 30 lines + "search this file instead, don't re-read it whole."
- **Why conditional:** Hestia already promotes large tool outputs to artifacts, which solves the
  overflow differently (and arguably better). The *behavioral nudge* ("narrow with grep instead
  of re-reading") is the part worth borrowing — fold it into the artifact-promotion message so
  the model is told *how* to proceed, not just that the output was truncated.
- **Effort:** Small (message/UX tweak on existing artifact path).

### T2.4 — Per-model profiles as a first-class config object.
- **What:** Both keep per-model profiles (context limit, thinking budget, skill/knowledge token
  budgets) — little-coder `local/config.py::MODEL_PROFILES`, smallcode `profiles/*.toml`.
- **Why conditional:** Hestia's config is per-deployment (one model at a time), so this is
  lower-urgency. But if you'll swap between the 35B-A3B (coding) and a smaller/faster model
  (chat/voice), a `ModelProfile` that bundles ctx size + reasoning budget + calibration numbers
  is cleaner than editing `config.runtime.py` each time. Pairs with the existing two-number
  calibration (ADR-011).
- **Effort:** Small-to-medium.

### T2.5 — Knowledge / tool-usage "skill" injection, query-scored and budget-gated.
- **What:** little-coder scores small markdown cheat-sheets (algorithms, per-tool usage notes)
  against the user message and injects 1–2 within a strict token budget (`skill_augment`,
  `knowledge_augment`).
- **Why conditional:** Hestia has memory epochs + style prefixes (similar machinery), so the
  injector exists in spirit. The coding-specific value is the *tool-usage* skills ("how to use
  edit_file correctly") injected on error/recency — a cheap way to improve tool hygiene without
  bloating the system prompt. Reuse the epoch injection path rather than building new.
- **Effort:** Small if layered on memory epochs.

---

## 4. TIER 3 — Leave on the table

- **Model escalation to cloud on hard-fail** (smallcode `escalation.js`). Directly contradicts
  Hestia's local-first, no-default-cloud-dependency thesis. Skip. (If ever wanted, it's a clean
  opt-in tool, but it's not a fit for the project's identity.)
- **smallcode's MarrowScript / `marrow/` DSL and the "compiled" layer.** Their own docs admit
  it's partly a design-discipline fiction. No reason to adopt a bespoke DSL; just take the ideas
  in plain Python.
- **Governor "Bayesian tool scoring" (trust_decay, tool_scorer).** Cute, unproven, adds stateful
  complexity. The deterministic quality-monitor (T1.4) captures 90% of the value with none of the
  learning-system risk.
- **Two-stage tool routing / category selector** (smallcode `two_stage_router.js`). It trades a
  round-trip to shrink the tool schema for ≤16k-context models. You're running **131k context** —
  token pressure from tool schemas is a non-issue. Not worth the extra latency on a slow local
  model. (Hestia's existing capability-based tool filtering is already enough.)
- **Evidence store / cite-before-answer** (little-coder `evidence/`). Built for the GAIA
  benchmark's citation requirement. Hestia's egress audit + memory already cover provenance for
  the assistant use case. Skip unless you specifically chase QA benchmarks.
- **BoneScript "one file → whole backend"** (smallcode). A scaffolding gimmick orthogonal to
  Hestia. Skip.
- **TUI / fullscreen alternate-buffer / command palette** (both). Hestia's surfaces are
  Telegram/Matrix/CLI/web — a coding TUI is a different product. Skip.
- **Vague-input clarify guard** (smallcode regex classifier → "ask for clarification"). Mildly
  nice, but Hestia's persona is already "direct, ask when ambiguous," and over-eager clarify
  prompts annoy on chat platforms. Low priority; not worth a dedicated subsystem.

---

## 5. The "should Hestia do coding at all" question

Hestia's architecture is assistant-shaped (turn state machine, platform adapters, policy/trust,
voice). Adding coding does **not** require a rewrite — it's:

1. A **tool cluster**: `edit_file`, `glob`, `grep`, optional `run_tests`/`lint` (T1.1, T1.5, T2.2).
2. A few **harness-robustness upgrades** that help *all* turns: JSON repair (T1.2), thinking-budget
   abort (T1.3), quality-monitor (T1.4).
3. A **safety net** for unattended edits: per-turn checkpoint/rollback (T1.5).

The trust model already exists to gate destructive file ops; the calibration + context builder
already manage the budget; the slot manager already handles concurrent sessions. Coding slots
into the existing skeleton.

**Caveat worth stating plainly:** running a coding agent against a *real repo* unattended is more
dangerous than the current assistant workload. The v0.12 review already flagged that headless
`write_file` is single-gated (H1) and the token-count cache miscounts tool-call messages (C1).
**Fix C1 and H1 before pointing Hestia's edit tools at anything you care about** — a miscounted
context on a coding turn means truncated diffs, and an ungated headless write means an unattended
overnight run can clobber files. The checkpoint/rollback (T1.5) is the seatbelt.

---

## 6. Recommended sequencing (Kimi-friendly, sequential)

Each is an independent loop; ordered so early ones de-risk later ones.

1. **`edit_file` tool + write-on-existing guard** (T1.1) — the single biggest capability gap.
2. **JSON-repair tool-call fallback** (T1.2) — cheap, helps every turn immediately.
3. **`glob` + `grep` tools** (T1.5a) — needed for the model to navigate a repo.
4. **Quality-monitor with targeted corrections** (T1.4) — turn-savings on every stuck turn.
5. **Mid-stream thinking-budget abort** (T1.3) — wall-clock savings; touches streaming, do after
   the cheaper wins.
6. **Per-turn checkpoint + rollback** (T1.5b) — the safety net before unattended coding runs.
7. *(Then, only if coding becomes recurring)* plan-tracker anchor (T2.1), test-runner/LSP (T2.2),
   per-model profiles (T2.4), tool-usage skill injection (T2.5).

Prereqs from the v0.12 review: **C1 (token cache)** and **H1 (headless write gate)** should land
before step 6, ideally before step 1.

---

## Appendix — file references for whoever implements these

little-coder (TypeScript pi-extensions, the better-evidenced harness):
- `.pi/extensions/write-guard/index.ts` — write-refuses-existing + path normalization (T1.1)
- `.pi/extensions/output-parser/parser.ts` — `repairJson` + text/fence/tag extraction (T1.2)
- `.pi/extensions/thinking-budget/index.ts` — mid-stream abort + commit nudge (T1.3)
- `.pi/extensions/quality-monitor/quality.ts` — failure taxonomy + corrections (T1.4)
- `.pi/extensions/read-guard/index.ts` — read-overflow trim + "search instead" nudge (T2.3)
- `docs/architecture.md`, `docs/benchmark-qwen3.6-35b-a3b.md` — design + the key benchmark

smallcode (JS, idea mine — verify before copying):
- `ARCHITECTURE.md` — the clearest prose on *why* each mechanism exists
- `src/governor/early_stop.js` — patch-spiral / read-loop / greeting-regression detection (T1.4)
- `src/session/plan_tracker.js` — ACTIVE PLAN anchor (T2.1)
- `src/tools/two_stage_router.js` — category routing (T3, skip for 131k ctx)
- `src/session/snapshot.js` / `undo.js` — per-turn checkpoint/rollback (T1.5b)
- `bin/escalation.js` — cloud escalation (T3, skip — violates local-first)
