# Ideas & Future Directions — Hestia

**Audit date:** 2026-08-22 · **These are speculative proposals, not defect findings.** Everything here is optional; the fix-first backlog lives in `11_IMPROVEMENT_OPPORTUNITIES.md` and `12_PRIORITY_ROADMAP.md`. Each idea notes the audit observation that motivates it and the main risk.

---

## 1. The Action Registry: ADR-042 finished properly

**Motivation:** the gate map (`08` §2) shows Hestia already has one implicit concept — "a side-effecting action with declared capabilities" — expressed four different ways (tool handlers, workflow nodes, delegation, recovery writes). Fix A1 makes the registry the chokepoint; going further, make *every* side effect a registered **Action** with declared capability labels, confirmation semantics, egress/file/scope metadata.
**Payoff:** uniform audit, dry-run, policy explanation, and permission declarations for external tool modules (ADR-051 plugins could declare "needs: network, filesystem:Documents"). Confirmation UI, blocked-actions digest, and the proposed effective-policy viewer all read from one source of truth.
**Risk/effort:** large-ish refactor; do it incrementally by moving existing tools onto the declaration schema first, behaviors second. Only after the roadmap's A1 lands.

## 2. Unified Execution Journal ("what did Hestia do and why?")

**Motivation:** turn transitions are journaled beautifully; workflows persist only terminal states; maintenance has its own trace store; scheduler actions are reconstructable only from logs. Four timelines where one would do.
**Proposal:** a single `activity` view joining turn_transitions, workflow node results (post-B4), maintenance_trace, scheduler fires, and capability events — queryable by session/workflow/user/time, rendered as one timeline in the dashboard. Not new data collection at first: just a federated read model over stores that already exist.
**Payoff:** transforms operator debugging from archaeology to lookup; makes the observability inventory (already strong) coherent.
**Risk:** low (read-only federation first); becomes more valuable automatically as B4 lands.

## 3. Workflow engine v2: durable executions & replay

**Motivation:** B4 adds RUNNING-state persistence; the natural endpoint is event-sourced executions — trigger payload + node results appended, replay/resume from any point, idempotency keys per trigger delivery.
**Proposal sketch:** keep the DAG executor; add `execution_events` appends; on restart, sweep RUNNING → resumable rather than FAILED; "replay from node X" button in the editor re-runs downstream of any node using recorded upstream outputs. This also gives test-runs their natural form: same machinery, `is_test` sink.
**Payoff:** workflows become trustworthy for long-running automations (job scrapers, email digests) — currently the riskiest thing to build in Hestia.
**Risk:** scope creep; gate behind the B4 milestone.

## 4. Dry-run / simulation mode everywhere

**Motivation:** BUG-041 (test runs have production effects), SEC-022 (destinations from inputs), interpolation silent-empty (BUG-069). All three share a root: no way to *see* what an execution would do without doing it.
**Proposal:** a simulation context handed to Actions (idea #1): send_message renders to preview pane; http/tool calls return mocked descriptors; interpolation failures surface loudly. Start with workflows ("Preview run" beside Test run), extend to scheduled tasks ("next fire preview").
**Payoff:** editor trust; kills the test-pollution problem class entirely.

## 5. Natural-language workflow authoring via the proposals system

**Motivation:** the reflection loop already mines patterns into proposals with accept/reject/defer; the editor is powerful but demands graph-thinking (UX-001).
**Proposal:** "Hestia, when a job alert email arrives, summarize it and send me the top three" → proposal containing a generated workflow draft (schema-validated, gated nodes only, destinations pinned to owner) → accept opens the visual editor with the draft loaded for review before activation. Human approves twice (draft + activation); the trust system stays authoritative.
**Risk:** LLM-generated graphs need strict validation (BUG-071's save-time validation is a prerequisite).

## 6. Voice-first parity

**Motivation:** voice turns are second-class today (confirmations auto-denied BUG-014, channel misattribution, typing-target bug BUG-063) despite the pipeline's defensive quality.
**Idea:** once fixed, push further — spoken confirmations with TTS-rendered argument summaries ("Approve sending email to X?"), voice-driven workflow triggers. Differentiates Hestia from every dashboard-only assistant; the STT/TTS scaffolding already exists.

## 7. Model routing: right-size the judges

**Motivation:** reflection judges, dedupe/contradiction passes, style learning, and llm_decision nodes all use the primary 35B slot model. Token cost and slot contention (the live box runs `-np 3`) mean background intelligence competes with conversation.
**Idea:** inference client gains named profiles (main/judge/embed); judges route to a small local quant (or llama-server embeddings endpoint where applicable). SlotManager untouched; profile selection at call sites that already know their role.
**Prerequisite:** token-accounting truthfulness (C2) so savings are measurable.

## 8. Mid-term memory layer between epochs and raw history

**Motivation:** epochs cover ~30 days compressed; raw window covers recent turns; the gap (weeks-to-months detail) is served only by FTS5 recall, which requires the model to know what to ask.
**Idea:** rolling weekly summaries (same soft-delete/reversible discipline) injected as a third prefix layer; compaction archives already hold the raw material. Watch budget: layer must be aggressively capped (~200 tokens) to avoid recreating the growth problem.

## 9. Household identity profiles

**Motivation:** multi-user support exists (users, identities, roles) but trust presets are global-with-overrides; `prompt_on_mobile` hints at per-context trust nobody fully uses.
**Idea:** per-member trust presets and quiet-hours; dashboard "household" page showing who can do what where. Prerequisite: SEC-010 fail-closed scoping and §4 authz gaps — this idea is the payoff for that hardening.

## 10. Regression fixture library as a product feature

**Motivation:** the degeneracy breakers already capture regression fixtures at failure sites (orchestrator audit, done-well #2); they're invisible to the operator.
**Idea:** dashboard page listing known failure modes with one-click replay against current code/config; doubles as acceptance checks after model swaps. Cheap because capture exists.

## 11. Chaos fakes for llama-server

**Motivation:** BUG-003/021/022 are all "server misbehaves" paths the suite doesn't exercise; the Aug-13 crash forensics show real-world llama instability is normal.
**Idea:** a `ChaosInferenceClient` fake (stall mid-stream, error chunks, connection drops, malformed SSE, slow tokenize) wired into integration tests; optionally a manual `hestia debug chaos` toggle. Converts the reliability findings' fixes into regression-proofed behavior.

## 12. Property/fuzz testing for the two parsers that matter

**Motivation:** FTS5 sanitizer (BUG-011/073/074) and the four-format tool-call text parser both parse adversarial input; both have example-based tests only.
**Idea:** hypothesis-style property tests ("sanitizer output never raises MATCH errors"; "parser recovers any well-formed variant"). Small effort, directly targets confirmed bug classes.

## 13. Remote-access story beyond Tailscale-by-discipline

**Motivation:** dashboard binds 0.0.0.0 with auth+2FA; posture guard enforces the floor. Mobile UX exists but session codes still travel via Telegram/Matrix.
**Idea:** document-or-build a proper remote profile: loopback-bind + reverse-proxy guidance, or a pairing flow (device shows code → approve in chat) making mobile access first-class without widening attack surface. Low priority; mostly documentation today.

## 14. Cost & quality dashboards

**Motivation:** traces carry tokens/outcomes/durations but nothing aggregates them; PERF accounting is blind on streaming turns until C2 lands.
**Idea:** dashboard cards: tokens/day (per user/session), p50/p95 turn latency, breaker-firing rates, maintenance outcomes, egress anomalies. Mostly SQL + one page; makes regressions like calibration drift visible immediately.

## 15. Simplification horizon (things to retire eventually)

- Matrix hand-rolled command parsing → shared parser (B6) then delete.
- Three scheduler callback factories → one (delete-list).
- `inference` legacy workflow node → migrate to llm_decision/tool_call then remove (URL-extraction heuristic is a data-mangler).
- Config-as-Python runtime divergence → shrink toward env-layer-only overrides if the dual-worktree pain ever grows.
- Alembic: either regenerate a snapshot baseline or remove loudly; ambiguity is worse than absence.

---

**Sequencing note:** ideas #1–#5 form a coherent arc (Action Registry → journal → durable executions → simulation → NL authoring) that would compound; each is valuable alone, and each depends on the corresponding fix-first item landing (A1, B4, BUG-041/071) — fix the foundation, then build the product on it.
