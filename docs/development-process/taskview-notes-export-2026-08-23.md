# TaskView note bodies — active cards, goal 1 "Hestia"

**Captured 2026-08-23.** Verbatim note text for all 25 active cards, so a board delete/recreate loses nothing. Paste these back as the `note` field.

---

## #44 — L245: allowlist-only tool authorization for unattended channels + gate chokepoint (ARCH-001)
**Column:** In Review · **List:** Runtime · **Priority:** High

This card's note is long and is the system of record for the L245 loop. It is reproduced in full at the end of this file (see APPENDIX A) because of its length.

---

## #45 — L246: test-blindness audit (what passes all gates and is still wrong)
**Column:** Backlog (suggest Spec'd) · **List:** Runtime · **Priority:** High

Reproduced in APPENDIX B.

---

## #32 — M1: remove Workflow.trust_level (blocked by #44)
**Column:** Spec'd · **Priority:** Med

DECISION CONFIRMED 2026-08-23: REMOVE trust_level. allow_listed_tools is the unit of authorization for a workflow.

Originally decided 2026-07-03 on the grounds that trust_level was decorative. That reasoning was revisited after the audit-remediation merge added workflow gating (#49), and it holds. Confirmed rationale:
- There are already TWO per-workflow fields and only one works. allow_listed_tools is read in executor.py at two call sites and passed to gate.check as allow_list. trust_level is stored, validated against _TRUST_LEVELS, serialized in the API, and read by nothing that makes a decision.
- A trust preset is a property of a person, not a job. The gate resolves trust from user.trust_preset. Adding a second resolution keyed on the workflow creates a conflict (user says paranoid, workflow says developer) whose every answer is either a privilege escalation path or a confusing no-op.
- Presets only produce auto_approved, which is meaningless on an unattended channel with no confirmation surface. On unattended channels the destructive path never reaches _resolve_trust at all; it allow-lists or denies and returns.
- An explicit tool list is more auditable than a preset name.
- Two overlapping per-workflow controls is the duplication class the audit spent a section on.

BLOCKED BY #44, for sequencing only. ADR-052 §3 now answers the scope question it was waiting on, so this is unblocked once #44 merges.

Removal scope:
- src/hestia/workflows/models.py: remove the trust_level field (~L56).
- src/hestia/web/routes/workflows.py: remove trust_level from the serialized response (~L107), the create validation + _TRUST_LEVELS constant (~L206-210, L220), and the update path (~L293-300).
- src/hestia/workflows/store.py: stop writing/reading trust_level (serialization ~L92, column list ~L108, row mapping ~L356).
- Frontend: remove trust_level from the workflow create/edit form, any display, and the API client type.
- tests/unit/workflows/test_executor_trust.py sets trust_level="paranoid"/"household" as a fixture attribute; those tests need updating. Make sure the replacement still exercises allow_listed_tools deny AND allow paths.

DB column: do NOT write a destructive DROP COLUMN migration. Leave the column dormant (additive runtime migrations). Existing rows keep their value; it is ignored.

Tests (first): workflow create/get/update round-trip works with no trust_level in the API shape; a workflow persists and reloads without it; an existing row that still has a stored trust_level loads fine (value ignored).

Rules: tests-first, gates green, no merge/push without Dylan's okay, per-item accounting, no silent skips.

---

## #46 — Migration/schema drift detector; the fresh-db smoke test is vacuous
**Column:** Backlog (suggest Spec'd) · **List:** Runtime · **Priority:** Med

Source: docs/development-process/reviews/audit-remediation-r1-round2-2026-08-23.md finding A. Also the concrete form of audit F8/F9 and TEST-007.

PROBLEM. tests/unit/persistence/test_migrations_registry.py::test_migration_chain_runs_clean_on_fresh_db does not test the migration chain. db.create_tables() is metadata.create_all from schema.py AND THEN apply_runtime_migrations. Both workflow_executions.is_test (schema.py L264) and workflows.allow_listed_tools (L192) are declared in schema.py, so on a fresh database those columns exist before any migration runs. The column assertions pass with MIGRATIONS = []. The exact m010 defect that motivated the test would still go green.

Not fully vacuous: idx_messages_session_idx and idx_sessions_last_active are not in schema.py, so those two assertions do exercise m009. But the part aimed at the finding does not exercise the thing it names.

The defect class IS closed, by test_every_defined_migration_is_registered, which is correct and catches m010 directly. So this is false confidence rather than an open hole. It still needs fixing, because a test named for a finding it cannot catch retires that finding.

FIX, in order:
1. Test the upgrade path, not the fresh path. Build a database, drop the columns the migrations add, run apply_runtime_migrations, assert they come back.
2. Better, the drift detector this is really reaching for: build database A from metadata.create_all alone, database B from the oldest schema snapshot plus the full migration chain, assert the two schemas are identical (columns, types, indexes).

Why (2) matters more: it closes drift in BOTH directions. m010 was "migration exists, unregistered, column present in schema.py," so fresh installs worked and every existing DB would have broken. The mirror image, a column added to schema.py and never given a migration, has the same blast radius and is STILL uncovered. A schema-equality assertion catches both and needs no per-column maintenance.

The repo has no harness for constructing an old database, which is why the test took the shape it did. Building that harness is the actual work here (TEST-007: Alembic has zero replay/downgrade coverage).

NOTE 2026-08-23: L245's m011 backfill test DID take this lesson — it seeds pre-L245 rows and runs the migration twice rather than leaning on create_tables. Use it as the model.

Rules: tests-first, gates green, no merge/push without Dylan's okay.

---

## #47 — Small cleanups from the audit-remediation round-2 review
**Column:** Backlog · **List:** Runtime · **Priority:** Low

Source: docs/development-process/reviews/audit-remediation-r1-round2-2026-08-23.md finding B and the nits section. All small; bundle into one loop. APPEND, do not overwrite.

1. (The real one) test_cancelled_turn_does_not_leak_lock_reference reimplements the code it tests. It builds its own coroutine and the docstring says "Mirrors engine.process_turn: acquire -> async with -> finally unref." It proves the pattern works; it does not prove engine.process_turn uses the pattern. Move unref back outside the finally in engine.py and this test still passes green. Fix: create a task calling orchestrator.process_turn, cancel it mid-turn, assert manager._refs is empty. tests/unit/orchestrator/test_concurrency.py already drives real turns elsewhere in the file, so the machinery exists. See #45 for the general rule.

2. DONE in L245 (f1a2802). _GATED_NODE_TYPES is now a single definition in tool_selection.py; the executor imports it. No action.

3. Stray triple blank line in executor.py _run_node. Harmless, but it means ruff's E303 is not enabled. Decide whether to turn it on. (Check whether L245 already cleaned the whitespace; the rule question stands either way.)

4. InferenceTimeoutError still renders as "The AI is taking longer than expected. Try again in a moment." On the streaming-stall path the user is looking at partial text above that message, and the wording implies nothing was produced. Add a distinct string for the interrupted-stream case, matching the "[response interrupted]" marker now persisted in history.

MOVED OUT 2026-08-23: the four L245 review-round-2 items (stale ADR-052, stale CHANGELOG line, ToolBlockedError/ValueError split, pre_gated check nested under the gate-bound condition) were moved to #44 as a pre-merge punchlist, since all four touch files that live on the L245 branch. Do not duplicate them here.

Rules: tests-first, gates green, no merge/push without Dylan's okay.

---

## #48 — Open decisions the audit remediation deliberately deferred
**Column:** Backlog · **List:** Runtime · **Priority:** Med

Source: docs/audit/REMEDIATION_SUMMARY.md "Deliberately NOT done (needs your decision)". Captured so the list does not get lost now that the branch is merged. Each item needs a call from Dylan before it can become a loop; the run correctly stopped at every one rather than guessing.

BEHAVIOR / UX
- BUG-044: auth-code digit filter scoping. May reverse a deliberate privacy choice.
- BUG-023: /reset cancellation semantics.
- BUG-045: the thinking-bubble prefix presentation.
- Reset-semantics unification between Telegram and Matrix (they still diverge).

WORKFLOWS
- Workflow duration ceilings and the cancel endpoint: needs actual values, not defaults.
- Webhook replay persistence (SEC-017).

SECURITY / POLICY
- F4: SUBAGENT channel trust classification. Also relevant to #44.
- SEC-011: curl_cffi model selectability.
- SEC-012: structured injection-flag propagation. The workflow gate call passes no injection_flagged, so webhook payload content that trips the scanner is not flagged on that path.

PERFORMANCE
- PERF-003: delta tokenization cache. The audit called this the largest recurring hot-path saving; the run judged it needed careful design rather than an overnight attempt. Agreed.
- Bundle route-splitting beyond what landed. Overlaps #41.
- openui removal.

DATA
- Retention windows for traces, capability_events, and egress. maintenance_trace TTL is wired; the others need window values.
- FK violation cleanup: 89 pre-existing violations measured in the live DB. Foreign keys remain OFF because enabling enforcement before cleanup risks runtime failures. WAL and busy_timeout applied per connection instead. Enabling FKs depends on cleaning those 89 rows first.

REPO
- escape_room_planning.md removal from git. Dylan's file, his call.

CHOICES MADE, worth conscious ratification (full list in REMEDIATION_SUMMARY):
- Streaming stalls now FAIL the turn instead of delivering a truncated answer. Partial text is persisted with an interrupted marker.
- Retries are non-streaming-only.
- Cron workflows fire via a per-minute scheduler heartbeat rather than first-class task registration.
- Matrix commands require exact token match (/resetnow is no longer /reset).
- Email poison messages park after 5 failures.
- Terminal child processes get an env allowlist (PATH/HOME/USER/SHELL/TERM/TMPDIR/locale).
- The login picker exposes platform names on the unauthenticated roster.

ONE THE REVIEW ADDED: the unauthenticated /available_users endpoint returns user_id, display_name AND platform names, with a per-user identity query. The same branch removed chat IDs from it as "an unauthenticated reconnaissance feed," so the branch moved in both directions at once. Chat IDs were the sharp part and they are gone, so net posture is better. Still a product call: keep it, return platforms only after a user is selected, or drop the picker and have the user type an identifier.

Rules: no merge/push without Dylan's okay.

---

## #49 — feature/audit-remediation-r1: external audit + overnight remediation (MERGED)
**Column:** Done · **List:** Runtime · **Priority:** Med

Record of what landed. The run itself could not create cards (no board access from that environment), so this is the retroactive entry.

WHAT IT WAS. An OpenRouter stealth model ("ox alpha", free for five days) produced a full-stack audit of the repo on 2026-08-22 (docs/audit/, 16 files, ~60 registered findings: 2 Critical, ~19 High, plus 16 performance, ~20 UX/a11y, 9 architectural, 8 testing items). It then ran unattended overnight fixing everything that needed no operator decision. Result: feature/audit-remediation-r1, 23 commits, 154 files, +8,037/-1,550, based on develop @ 6d36d45.

HEADLINE FIXES. BUG-001 session-lock pop race and BUG-002 slot-eviction race; SEC-001 workflow tool-node gating; streaming honesty (BUG-003/022/046); workflow execution lifecycle (RUNNING rows, self-trigger refusal, cron heartbeat, test isolation); SQLite pragmas and hot-path indexes; login recipient allowlisting and roster minimization; terminal env allowlist; web-ui work-loss prevention and a11y bundle; green gates restored (ruff 49→0, mypy 7→0, TS build fixed).

REVIEW. Two rounds, both in docs/development-process/reviews/:
- audit-remediation-r1-2026-08-23.md (round 1): four blockers, all fixed in f8b919a.
- audit-remediation-r1-round2-2026-08-23.md (round 2): merged with two follow-ups filed as #46 and #47.

THE FINDING WORTH REMEMBERING. m010_execution_is_test was defined but never appended to MIGRATIONS. The live instance would have crashed on the first save_execution insert. It passed ruff, mypy, 2,281 tests, and the model's own self-review; it was caught by re-reading the diff. Green gates are necessary and nowhere near sufficient. The branch referenced 59 finding IDs in src/ and added 37 test functions, so roughly two thirds of the fixes are asserted by comment, not pinned by a test. #45 goes after this class directly.

A SECOND PATTERN, three instances: asserting against a reimplementation instead of driving the real path. The capability gate reimplemented InvestigateNode._resolve (that was the round-1 security bypass); the cancellation test reimplements engine.process_turn (#47); the migration smoke test exercises schema.py rather than the migration chain (#46). Written into #45 as a hard rule.

WHAT THIS DID NOT CLOSE: ARCH-001. See #44. The deferred decision list is #48.

METHOD NOTE. The overnight run worked because the audit preceding it was specific: numbered findings, evidence, and an explicit "needs a human decision" boundary that the model respected at every item. The failure mode to watch is that an unattended agent optimizes for the signal it can see, and green gates were the signal. Before the next unattended run, spend the hour making the gates cover the thing you are most afraid of.

---

## #50 — Changelog: audit-remediation behavior changes + the #44 breaking change
**Column:** Backlog (suggest Spec'd) · **List:** Runtime · **Priority:** Med

GAP FOUND 2026-08-23: docs/CHANGELOG.md [Unreleased] is EMPTY. The audit-remediation merge (#49) landed 154 files with a dozen user-visible behavior changes and added nothing to it.

PART 1 — backfill [Unreleased] for what already merged.

Changed
- Streaming inference that stalls now FAILS the turn instead of delivering a truncated answer marked complete. The partial text is persisted with an explicit "[response interrupted]" marker.
- Transient-error retries are non-streaming-only.
- Matrix commands now require an exact token match: /resetnow is no longer treated as /reset. Trailing arguments still dispatch.
- Cron-triggered workflows now fire on their own schedule via a per-minute scheduler heartbeat. Cron-less and command-less triggers no longer match everything.
- Terminal child processes now run with an environment allowlist (PATH, HOME, USER, SHELL, TERM, TMPDIR, locale). WILL break existing terminal usage that relied on inherited env.
- Email messages that fail processing five times are parked instead of retrying forever.
- Workflow test runs are flagged is_test and excluded from last-execution aggregates.
- The web login picker sends codes to a server-resolved, allowlisted identity.

Security
- Workflow tool_call and investigate nodes now pass through the CapabilityGate before dispatch (SEC-001).
- chat_command triggers require an explicit command.
- send_message destinations pinned in node config win over interpolated inputs.
- Secret-looking keys in node configs are masked in the workflows and versions API responses.

Fixed
- Per-session serialization race that could let two turns run concurrently on one session (ADR-041).
- Slot eviction race that could cross-contaminate KV cache state between sessions.
- SQLite now applies WAL and busy_timeout per connection; hot-path indexes added. Foreign keys remain OFF pending cleanup of 89 pre-existing violations (see #48).

PART 2 — the #44 breaking change, when it lands.

Changed (BREAKING)
- Workflows, and other unattended channels, may now invoke only the tools named in their allowlist. Previously the gate restricted only shell, local-write, and email-send capabilities, so a workflow could freely call file-read, network-egress, memory, clipboard, scheduler, and self-management tools regardless of its allowlist. Allowlists are now derived from the workflow's node graph at save time and confirmed by the operator; existing workflows are backfilled on upgrade (m011). A workflow whose graph changes prompts for re-confirmation showing what it gains.
- investigate nodes take their tool list from node config only. Tools can no longer be supplied through node inputs.
- Workflow.trust_level is removed (see #32); allow_listed_tools is the sole per-workflow authorization control. The database column is left dormant rather than dropped.
- ToolRegistry.call requires a ToolCallContext; API clients calling it without one fail loudly. An unbound registry refuses enforce-mode calls.

CONTEXT: Dylan confirmed 2026-08-23 he has no workflows currently in use and no other known operators, so practical blast radius is near zero. Write the notes anyway: the changelog is what makes the repo credible to a first-time visitor (see #34), and a security-relevant default change with no entry is what erodes that.

NOTE: #44's pre-merge punchlist item P2 fixes a stale CHANGELOG line about the deleted "internal" mode. Coordinate so the two edits do not conflict.

Rules: docs only. No merge/push without Dylan's okay.

---

## #36 — Workflow cheap wins (W1–W4)
**Column:** Spec'd · **Priority:** Low

Source: audit-findings-2026-06-29.md W1-W4. Four independent items:
W1 record skipped nodes: emit a NodeResult status="skipped" instead of silently continue-ing.
W2 persist a running execution row: write a 'running' row with an id at start, update to terminal at end.
W3 cancel token: thread a cancel token into the executor loop + inference so a stuck workflow can be aborted; persist 'cancelled' as a terminal status.
W4 graph-semantics decision note (docs only): document the executor's actual behavior (any-merge, sequential branches, source_handle routing, edge.condition unused/removed).
Rules: tests-first (W1-W3), gates green, no merge/push without Dylan's okay.

UPDATE 2026-08-23 (audit remediation merge, see #49):
- W1 DONE. Skipped nodes now emit status='skipped' NodeResults (audit BUG-039).
- W2 DONE. Executions persist a RUNNING row upfront and finalize at completion/failure; serve sweeps rows left RUNNING after a restart (audit BUG-036).
- W3 STILL OPEN, with a companion: the duration ceiling and cancel endpoint were on the remediation run's "needs your decision" list because they need actual values. See #48.
- W4 STILL OPEN.
Remaining scope: W3 + W4.

---

## #42 — Salvage runtime fixes (5 groups) + inference error surfacing + bench harnesses
**Column:** Done · **Priority:** Low · **sourceUrl:** https://github.com/dylan-okeefe/hestia/tree/fix/runtime-salvaged

Branch: fix/runtime-salvaged (pushed to origin)

Commits:
- 0ca631df fix(runtime): salvage five fixes from job-search test sessions (meta-tool circuit-breakers, /reset [RESET] handoff marker, browser_interact scroll + validation, write_file maxLength 2000->50000, EventBus.publish_nowait)
- aaf6893b feat(inference): surface real cause when llama-server connection drops (InferenceConnectionError + TransportError translation + sanitize branch)
- e6e4971f chore(scripts): inference + voice benchmark harnesses

Verified: 58 salvaged-group tests, 28 inference-client/sanitize tests, 116 inference+orchestrator tests pass; ruff and mypy clean on changed files.

Note: live unit-file tuning (n-cpu-moe 12, tensor-split 63,37, MTP draft, persistenced guard) is on the machine only, not in this branch.

CLOSED 2026-08-23: verified all three commits are ancestors of origin/develop. Merged. Moved to Done.

---

## #43 — fix/runtime-salvaged: runtime fixes + STT/TTS overhaul
**Column:** Done · **List:** Runtime · **Priority:** Low

Branch fix/runtime-salvaged merged into develop (fast-forward to 04ea56bb).

Post-merge test-regression fixes landed on fix/develop-test-regressions:
- Commit 4388cc9c — fix(tests): repair develop test regressions after runtime-salvaged merge
- Full suite: 2298 passed, 12 skipped (two consecutive green runs).

Key fixes: TopicStore plumbing for make_save_memory_tool in test fixtures; HESTIA_ALLOW_DUMMY_MODEL fallback in AppContext.inference; MemoryEpochCompiler updated for get_for_epoch API + global-memory dedup; README tool list cleaned up; compaction e2e fake-inference injection fixed; tour coverage updated for /add-topic, /remember-global, /remove-topic, /topic; meta_call_tool hardened against unknown tool names.

BEFORE MERGE (original notes retained):
- Install espeak-ng at OS level before switching TTS to Kokoro.
- Telegram /reset still replays old handoff; only Matrix plants [RESET].
- Low-sev follow-ups: clamp Kokoro output, publish_nowait fallback, 50k write reliability.

CLOSED 2026-08-23: verified 04ea56bb and 4388cc9c are both ancestors of origin/develop. Merged. Moved to Done.
Note: publish_nowait was subsequently fixed in the audit-remediation branch (BUG-029, see #49).

---

## #37 — H1: pass confirmation callback explicitly (shared mutable state)
**Column:** Spec'd · **Priority:** Med

Source: audit-findings-2026-06-29.md H1. AppContext.confirm_callback is shared mutable instance state set by set_confirm_callback and read in make_orchestrator, so in multi-platform serve the last setter wins and a later orchestrator/delegated subagent can pick up the wrong platform's confirmation path. Fix: pass the confirmation callback explicitly into make_orchestrator() and into delegate-tool construction, rather than through shared state. Tests: two platforms in one serve each get their own confirm path; a subagent does not inherit the wrong one. Rules: tests-first, gates green, no merge/push without Dylan's okay.

---

## #35 — Ship SOUL.example.md; gitignore the operator persona
**Column:** Spec'd · **Priority:** Low

Source: audit-findings-2026-06-29.md Nice-polish (public-readiness). Operator-specific persona content (SOUL.md — the "Silas" persona) ships in the public repo. Fix: gitignore SOUL.md and commit a sanitized SOUL.example.md, mirroring the config.runtime.example.py pattern from #14. Confirm with Dylan before untracking SOUL.md (his runtime keeps its copy). Rules: no merge/push without Dylan's okay.

---

## #34 — H7: open-source onboarding honesty (README/quickstart/CI/metadata)
**Column:** Spec'd · **Priority:** Med

Source: audit-findings-2026-06-29.md H7 (public-readiness, high value for the public-launch week). README uses <repo-url>; uv sync does not pull all feature deps; local config gitignore (done via #14); frontend tests not in CI; deploy docs conflict with the runtime-migration story; no PyPI/project metadata. Fix: rewrite Quick Start by mode (CLI / platforms / web), fix the clone URL, align deps and the migration docs, add the web-ui test job to CI, add project metadata. This is what makes the repo credible to a first-time visitor after the walkthrough video. Rules: no merge/push without Dylan's okay.

---

## #33 — C4: security docs — real disclosure + threat-model/hardening guide
**Column:** Spec'd · **Priority:** Med

Source: audit-findings-2026-06-29.md C4 (Critical, public-readiness). SECURITY.md still uses security@example.com; docs/guides/security.md covers mainly prompt-injection annotation, not the trust/auth model, filesystem/terminal risk, or deployment hardening. Fix: replace the placeholder with a real disclosure path, and write a concise threat-model + hardening guide (trust profiles, auth, loopback/exposed posture per #31, capability gate, fs/egress caveats). Video-week relevant: anyone visiting the repo after the walkthrough will look at SECURITY.md. Rules: no merge/push without Dylan's okay.

NOTE 2026-08-23: ADR-052 (allowlist-only authorization) is now the authoritative description of the workflow trust model and should be referenced by this guide.

---

## #41 — Nice UI polish (ConfirmDialog, shared Button, route code-splitting)
**Column:** Backlog · **Priority:** Low

Source: audit-findings-2026-06-29.md Nice-polish. Low-risk frontend cleanups: standardize destructive actions on the existing ConfirmDialog instead of window.confirm; use the shared Button component consistently; add route-level code splitting for heavy SPA pages if bundle size hurts. Some may be worth folding into the UX-polish pass (#1). Rules: no merge/push without Dylan's okay.

---

## #40 — M2: filesystem/egress hardening (only if internet-facing)
**Column:** Backlog · **Priority:** Low

Source: audit-findings-2026-06-29.md M2. Backlog / gated on intent. Path checks are resolve-before-open and the SSRF guard acknowledges DNS-rebinding gaps (matches ADR-045 best-effort). Acceptable for local-first; only worth doing if internet-facing becomes a real goal: fd-based no-symlink opens (O_NOFOLLOW) for file tools; pin resolved IPs or route egress through a hardened proxy. Do NOT prioritize for the local-first walkthrough. Rules: no merge/push without Dylan's okay.

---

## #39 — Frontend/type-safety backlog (H5, H6, M5)
**Column:** Backlog · **Priority:** Low

Grouped backlog from audit-findings-2026-06-29.md — maintainability, mostly post-launch (some overlaps UX polish #1):
H5 loose web API/frontend types — add Pydantic request/response models on the backend; a shared typed API layer on the frontend (replace dict[str, Any] routes and unvalidated res.json()).
H6 inconsistent frontend data fetching — one caching/deduping pattern (extend useApiQuery to cache by key), stop refetching tools/users/platforms in dropdowns.
M5 Knowledge.tsx too large — add identity selection, split into a data hook + table/section/modal components.
Rules: each its own spec + tests when queued; no merge/push without Dylan's okay.

---

## #38 — Backend architecture/reliability backlog (H2, H3, H4, M3, M4)
**Column:** Backlog · **Priority:** Low

Grouped backlog from audit-findings-2026-06-29.md — post-launch refactors. Each becomes its own loop when picked up:
H2 schema ownership split — make one bootstrap path authoritative for all table DDL (currently split across schema.py, store create_table(), runtime migrations). Also unblocks the full external-schema seam framework (see #27).
H3 AppContext coupling — split composition into service groups (core stores/events, agent runtime, platform runtime, web runtime) behind a thin facade.
H4 shutdown lifecycle — ordered teardown: stop accepting work, drain turns/events, stop adapters/scheduler/triggers, close DB/inference.
M3 TurnExecution size — extract retry/timeout/tool-dispatch/streaming helpers, behavior preserved.
M4 web global singleton — FastAPI lifespan/app-state + narrow service ports (only if scaling the web server).
Rules: each is its own spec + tests when queued; no merge/push without Dylan's okay.

NOTE 2026-08-23: H2 (schema ownership) is directly relevant to #46. The fresh-vs-migrated schema drift #46 describes is a symptom of the split H2 names.

---

## #28 — Pull job-URL extraction out of workflows/executor.py into a private tool
**Column:** Done · **Priority:** Low

Branch: feature/l243-extract-job-url-private-tool

Verified:
- Removed `_JOB_URL_PATTERNS`, `_IGNORE_URL_PATTERNS`, `_extract_best_job_url`, and the `extract_url` node special case from `src/hestia/workflows/executor.py`; generic `_extract_url_from_text` remains for reasoning fallback.
- Private tool `extract_job_url` exists in `~/code/hestia-tools/hestia_tools/job_url_extraction.py` and is registered in `hestia_tools/__init__.py`.
- Quality gates pass: ruff check/format and mypy clean on the changed file.
- Private repo tool tests pass (8 assertions) when run with the Hestia venv.
- Hestia tests/unit/workflows/test_executor.py had 25 pre-existing errors from the fixture using HestiaConfig.default() without inference.model_name = "dummy" / HESTIA_ALLOW_DUMMY_MODEL=1; unrelated to this change (subsequently fixed, see #29).

---

## #27 — DECIDED: extend the seam (setup hook) — job_alert migration unblocked
**Column:** Done · **Priority:** Med

DECIDED and IMPLEMENTED (L241): option 1, extend external-tool-modules seam with setup(context) hook. Merged to develop.

This card is complete; implementation work continued in #26 (job_alert migration) and the deferred full-framework loop (post-H2).

---

## #24 — Create batch add TaskView tool calling capability
**Column:** Backlog · **Priority:** Low

Add a tool-calling capability to support batch creation of tasks in TaskView, likely for use within the hestia-dev-notes workflow. Needs schema design, MCP tool integration, and validation.

---

## #7 — Approval queue / workflow suspend-and-resume
**Column:** Spec'd · **Priority:** Low

Parked future work: approval queue and workflow suspend-and-resume. Source: docs/roadmap/future-systems-deferred-roadmap.md (Tier A9). Depends on CapabilityGate audit + workflow executor.

NOTE 2026-08-23: L245 (#44) delivered the CapabilityGate chokepoint this depends on. Also relevant: on unattended channels requires_confirmation is now defined as DENY because there is no confirmation surface. An approval queue is exactly the surface that would let those escalate instead of failing.

---

## #6 — Future scope-promotion pass
**Column:** Backlog · **Priority:** Low

Parked future work: scope-promotion / proposal-to-trusted promotion mechanics. Source: docs/roadmap/future-systems-deferred-roadmap.md (Tier A9 and policy synthesis).

---

## #1 — Web UI: UX polish
**Column:** Backlog · **List:** Web UI · **Priority:** Med

Source: docs/reviews/web-ui-ux-review-2026-06-16.md (UX-polish split). Items: humanize raw IDs app-wide (workflow versions, room/telegram/session IDs, Errors source); loading states on all async actions (Check Now, Stream, health checks, Run audit, Process Preview, Run now, Save Notes); Errors timestamp column + default sort newest-first; Browser Sessions sortable columns + filter; Dashboard "System Health: Unknown" should reflect real health; Scheduler task-row verbosity (short title + expand) and stale past "Next Run" on disabled tasks; Workflows Edit/Open affordance; duplicate "Audit Findings" header on Security & Health; Context Lab guidance; empty session titles; nav grouping. Next: turn into an implementation prompt.

NOTE 2026-08-23: the audit-remediation merge (#49) already landed part of this surface (work-loss prevention, error boundary, a11y bundle, editor hygiene, Defer button). Re-scope against current main before queueing.

---

# APPENDIX A — #44 full note

See the card note captured in `docs/development-process/reviews/l245-gate-chokepoint-2026-08-23.md` plus the ADR at `docs/adr/ADR-052-allowlist-only-tool-authorization-for-unattended-channels.md`. The card note is the concatenation of: the scope decision, the ox-alpha addendum, Claude's adjudication of that addendum, the implementing model's delivery report, review round 1 (four findings, all closed in f1a2802), and review round 2 (the pre-merge punchlist P1–P4). It is reproduced verbatim in the board at time of capture; if lost, reconstruct from those two repo files plus this snapshot's summary of P1–P4:

P1. ADR-052 §2 is stale: still documents the deleted `internal` mode and `gate.audit_internal`. Rewrite to the shipped two-mode design (enforce / pre_gated, pre_gated bound to a tool name).
P2. CHANGELOG.md ~line 23 stale for the same reason.
P3. ToolBlockedError collapsed into ValueError in the pre_gated check: split tool-mismatch (ValueError, correct) from policy denial (must stay ToolBlockedError, since investigate.py:84 and executor.py:313 catch it). Update the registry.call docstring Raises: block for the new RuntimeError and ValueError.
P4. The pre_gated binding assertion sits inside `if self._gate is not None:`, so an unbound registry with a pre_gated context runs no checks. Hoist it out; better, raise for an unbound gate in both modes.

# APPENDIX B — #45 full note

Reproduced in the board at time of capture. Key structure, if lost:

PREMISE: not a coverage audit — docs/audit/09_TESTING_QUALITY.md already did that. The question is narrower, with a worked example: m010 was defined but never appended to MIGRATIONS, would have crashed the live instance, and passed ruff, mypy, 2,281 tests and a self-review. Find every other defect in that class.

SEED CLASSES: (1) registration lists, (2) cross-module contract duplication, (3) code/schema drift, (4) fail-open defaults, (5) asserted-by-comment-only.

DELIVERABLE PRIORITY: detectors before tests. Meta-tests that make whole classes impossible. NOTE: the node-type classification detector originally scoped here was DELIVERED IN L245 (test_every_node_type_is_classified); do not rebuild it.

HARD RULE: a test must drive the real entry point. No test may contain a comment saying it mirrors, models, or matches production code.

GUARDRAILS: every new regression test demonstrated failing against pre-fix code, reported per test; cap at 25 new tests ranked by defect class closed; no new fakes or mocks without an explicit flag.

OPTIONAL: mutation testing (mutmut/cosmic-ray) scoped to orchestrator/, policy/, persistence/ for ground truth rather than a model's guess.

SEQUENCING: two runs — audit produces the register plus detector list for review, then a fix run against the reviewed list.
