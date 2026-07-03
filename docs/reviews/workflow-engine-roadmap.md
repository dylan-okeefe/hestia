# Workflow engine roadmap — the platform bets

**Status:** discussion doc, not decided. Companion to
`audit-findings-2026-06-29.md`, which holds the cheap workflow wins (W1-W4).

This captures the larger workflow-engine findings from the orchestration-focused
audit. All of them are code-verified as accurate. None are bugs. Every one is a
"thin / implicit / not durable" observation, and each is a real investment, not a
quick fix. The point of this doc is to decide **whether** workflows become a
first-class product surface before spending on them, not to queue them
reflexively.

## The thesis (verified, and it is correct)

Hestia has two orchestration layers at different maturity. The chat turn
orchestrator is a mature local-agent kernel: explicit turn states, persisted
transitions, per-session locking, slot management, meta-tools, policy gates,
token budgeting, circuit breakers. The visual workflow engine is a practical
automation feature built beside that kernel: load active version, topologically
sort, run nodes sequentially, save the final result.

This split is not an accident. It maps to where the design effort went (the turn
runtime got the deep develop-review arc and ADR-040/041/042; workflows were built
as a feature). The audit read the history correctly.

## The central question to answer first

Are workflows meant to be a headline feature of Hestia, or a personal automation
convenience beside the agent runtime?

- If **convenience**: do W1-W4 (the cheap wins) and stop. Most of the items below
  are over-engineering for a single user running tens of workflows.
- If **headline feature**: the items below are the right end-state, and the
  convergence idea (one shared run lifecycle) is genuinely elegant.

The audit itself warns against bolting on Temporal-style enterprise machinery, so
even in the headline case the bar is "a polished local orchestration system," not
a distributed workflow engine.

## The bets (only if workflows go first-class)

### R1. A shared run-lifecycle abstraction under both turns and workflows
The elegant core idea: one "run" primitive with a run id, state transitions,
cancellation, trace events, tool/inference spans, artifacts, policy decisions, and
a failure bundle. Chat turns and workflow executions become specialized run
types. **Risk to weigh:** this refactors underneath the one part of the system
that already works best (the turn kernel), so it carries real regression risk and
should not be rushed. This is the biggest bet and everything else gets easier if
it lands first.

### R2. Full durable run state
Beyond the cheap `running` row (W2): per-node `node_started` / `node_finished` /
`skipped` / `cancelled` states persisted live, execution id exposed during the
run for polling, resumability considerations. Depends on R1 to be clean.

### R3. Formal, richer graph semantics
Beyond the cheap decision note (W4): decide any-vs-all merge as a real feature,
whether independent branches run in parallel (they are sequential today), branch
name validation, and whether skipped-node recording feeds a visual "what ran"
view. Do before adding many node types.

### R4. Node manifests / schema-driven node registration
Adding a node type today is multi-file choreography (backend class, frontend
component, editor defaults, property panel, tests, docs) with no shared contract,
so backend and UI will drift. A node manifest (type, label, config schema,
input/output schema, capabilities, branch handles, UI renderer hint,
timeout/retry policy) would drive both backend validation and frontend property
panels from one source. Worth it only if the node catalog is going to grow to
dozens.

### R5. Span-level observability and streamed progress
Today: aggregate per-turn traces and final workflow node results, plus a terminal
`workflow_completed` event. A real orchestration system needs span events
(`run_started`, `prompt_built`, `inference_started/finished`,
`tool_started/finished`, `node_started/finished/skipped`, `gate_decision`,
`artifact_created`, `run_cancelled`, `run_failed`) and workflow progress streamed
over SSE/WebSocket by execution id, so the UI does not wait for a full test run to
learn what happened. Pairs naturally with R1/R2.

### R6. Prompt and run reproducibility artifacts
Workflow LLM nodes build one-off prompts from JSON-serialized inputs; there is no
prompt template model, prompt hash, or prompt-debug view. Executions store
trigger payload, node results, token totals, and version, but not model name,
temperature, seed, prompt body, tool schema snapshot, or raw response. For
reproducible workflow runs: a prompt artifact model (rendered prompt, template
id/version, input variables, model config, prompt hash, token estimate, raw
response), model settings threaded into runs, optional full-prompt capture in
debug mode, tool schema hash, and a replay/export format for failed runs. Current
state is good enough for operational history, not for reproducibility.

### R7. Trigger indexing, bounded concurrency, resource classes
Verified pressure points for hundreds of workflows: `TriggerRegistry` holds
workflows in an in-memory list and `_match_workflows` scans them linearly;
matched workflows run sequentially per event; there is no global run-concurrency
limiter; schedule triggers match on cron/current-time rather than a
workflow-specific scheduled identity; interactive response state is in-memory.
Fixes: index triggers by type and key, add bounded run concurrency, add resource
classes (inference, browser, network, human_wait), persist pending interactive
waits, and add chain-depth/idempotency protection for `workflow_completed`
triggers (a workflow that triggers on workflow completion can loop). Only matters
at real scale.

## Audit's suggested sequence (if going first-class)

1. Shared run lifecycle (R1).
2. Durable run state and cancellation (R2; cancellation itself is cheap, W3).
3. Formal graph semantics and skipped-node recording (R3; recording is cheap, W1).
4. Node manifests / schema-driven registration (R4).
5. Span observability and streamed progress (R5).
6. Prompt/run reproducibility (R6).
7. Trigger indexing and bounded concurrency (R7).

## Open questions for us

- Headline feature or personal convenience? This gates everything above.
- If headline: is the shared run-lifecycle refactor (R1) worth the regression risk
  to the turn kernel, or do we grow the workflow runtime independently and
  converge later?
- Realistic workflow count: tens (stay as-is plus cheap wins) or hundreds (R7
  becomes real)?
- How much reproducibility do you actually want, operational history (today) or
  full replay (R6)?
