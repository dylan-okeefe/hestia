All eight deep-dive reviews are in, and I've cross-checked their findings against my own reading of the code plus the actual test/lint/type runs. Here is the consolidated review.

A note on ground truth I verified directly: uv run pytest gives 1701 passed / 29 failed, but almost all those failures are environmental — DNS is blocked in my sandbox so every http_get/web_search/egress test fails at name resolution, plus two genuinely stale tests (test_list_domains expects an old domain-normalization result, test_browser_stream asserts launch args that the code has since added). The backend agent running tests/unit -x saw 222 passed / 1 sandbox failure. So the suite is effectively green; there is no widespread breakage. Separately, mypy src/hestia reports 31 real errors across 11 files, and ruff reports 161 issues (97 are line-length E501, 18 are E402). That is the accurate baseline.

Prioritized summary — what matters most
These are the things I would fix before anything else, in order:

The trust posture in config.runtime.py is wide open and the agent runs unattended. TrustConfig(auto_approve_tools=["*"], preset="developer") with scheduler_email_send, subagent_shell_exec, etc. all true means a prompt injected via email, a Matrix room, or a workflow can run terminal, write_file, and email_send with no confirmation. The injection scanner only annotates untrusted content, it doesn't block. This is the single highest-risk item in the whole project. (Critical)

No per-session turn serialization. Orchestrator.process_turn has no lock. Rapid Telegram/Matrix messages, a scheduler tick overlapping a user message, or nested delegation can run two turns on the same session — same DB rows, same llama.cpp slot KV cache, same TurnContext. This is the most likely source of real-world corruption/flakiness on a live multi-channel deployment. (Critical)

Workflow tool nodes bypass the policy/confirmation gate entirely. workflows/executor.py:549 calls self._app.tool_registry.call(node.type, inputs) directly — _check_confirmation never runs. An email-triggered workflow with an email_send or terminal node executes unattended. (Critical)

Web dashboard binds 0.0.0.0 and the browser-stream WebSocket has an admin bypass. Runtime exposes the SPA/API on all interfaces, and browser_stream_ws only enforces the admin role if user_id is not None — a valid OTP token without a registry mapping skips the gate and can drive the live authenticated browser. (Critical / High)

reasoning_budget is dead config on the non-streaming path. InferenceClient.chat/chat_stream accept it but never put it in the request body. On a 12GB 3060 this means the policy's thinking limits don't actually constrain the model except via a client-side char heuristic in streaming. InferenceConfig.max_tokens is similarly never wired into the turn loop (it always uses the 1024 default). (High)

Scheduler can double-fire and hammer on failure. _tick lists due tasks and fires them, but next_run_at isn't updated until process_turn returns (minutes later), so the next 5s tick re-lists the same task; and on error next_run_at is left in the past, so a broken cron retries every tick forever. (High)

Two front-door problems for newcomers: README's Quick Start (pip install hestia) points at a package that doesn't exist and skips uv/llama.cpp/config/init entirely, and UPGRADE.md stops at v0.10.0 while the project is at v0.13.0. A fresh clone cannot get running from the README alone. (Critical for onboarding)

The web UI's home narrative is broken. The Dashboard's "Recent Sessions" stat actually counts workflow executions, there's no nav path to chat sessions, and ContextLab is fully built but unreachable (no route). (Critical for UX)

If you only do five things: tighten the runtime trust config, add a per-session turn lock, route workflow tool nodes through the policy gate, fix the WebSocket admin check + localhost bind, and rewrite the README Quick Start.

Backend correctness
The tool loop is genuinely well-defended against small-model misbehavior — JSON repair, XML <tool_call> fallback, meta-tool unwrap, circuit breakers for list_tools/describe_tool/identical calls, quality-pattern corrections. That work is real and good. The weaknesses are concentrated in concurrency and session/slot lifecycle.

Critical / High

Concurrent turns per session (no mutex) — orchestrator/engine.py process_turn, platforms/runners.py on_message, scheduler/engine.py _fire_task. Fix: per-session_id asyncio.Lock held for the turn. (Critical)
Shared IMAP connection is unsafe under concurrent async — email/adapter.py imap_session reuses an existing connection from a ContextVar; concurrent email tools dispatched via asyncio.gather interleave commands on one imaplib socket, and the poller + tools share one EmailAdapter instance (app.py:232). Fix: per-operation lock, or mark email tools ordering="serial", or never reuse across tasks. (Critical)
reasoning_budget / max_tokens not sent to llama.cpp — core/inference.py chat/chat_stream. (High)
Failed/partial turns leave stale slot KV cache — orchestrator/finalization.py:103. Slot save runs only on TurnState.DONE; on failure the live slot is neither saved nor erased, so the next turn reuses a HOT slot that diverges from persisted history. Fix: erase/rebuild slot on non-DONE finalization. (High)
finish_reason="tool_calls" with zero valid tool calls burns iterations — execution.py:183. When all structured calls fail JSON validation, the loop still enters _handle_tool_calls, persists an assistant message with no tools/results, and increments. Fix: if not chat_response.tool_calls, treat as degenerate and retry. (High)
correction=True flag is not persisted — there's no correction column in the messages schema, so after reload quality._is_read_only_streak treats injected corrections as real user input and its streak logic breaks. Fix: add the column (migration + read/write). (High)
Stale in-memory session cache — runners.py:153 caches user_sessions[platform_user] and never refreshes; Telegram clears it on /reset but Matrix has no equivalent, so archived sessions still accept append_message. (High)
Scheduler double-fire + retry storm — scheduler/engine.py _tick, persistence/scheduler.py update_after_run:249. (High)
Context window can emit invalid message sequences — context/history_window_selector.py. Multi-tool turns can pull the same assistant message in once per tool result (duplicate assistants), and orphan role:tool messages can be included without their assistant. Both violate the chat template. (High/Medium)
Medium

error_resolutions table exists only in Alembic, not in the create_tables/runtime-migration bootstrap path used in production — Web UI error resolve/ignore raises SQL errors on a fresh SQLite deploy (error_resolution_store.py, app.py bootstrap_db). Its list_statuses IN-clause also lacks bindparam(expanding=True).
email_inbound.py marks mail read before the workflow succeeds — failures lose the email.
HOT slot isn't validated after a llama-server restart (slot_manager.acquire); eviction proceeds even when slot_save failed, risking silent context loss.
memory/store.py save() allows unscoped memories (platform/user None) when called outside a turn, which search() then fail-closes and can never return.
Tool results are hard-truncated (execution.py:901) rather than summarized — conflicts with the project's own "never hard truncate" rule and can feed the model mid-sentence-cut tool output.
Low / nit: no inference retry/backoff on transient 5xx; naive-vs-aware datetime compare in list_due_tasks; turns.reasoning_budget column never written; _extract_file_path docstring typo. SQL injection: none found — stores are parameterized and dynamic column names are allowlisted.

Security
Strong primitives — http_get SSRF blocking (SSRFSafeTransport + non-global IP rejection), platform allowlists that default-deny, file-tool path sandboxing, secret masking in the config API, React text rendering (no dangerouslySetInnerHTML). The systemic gap is that Hestia treats the LLM as a privileged operator and the unattended paths remove the human from the loop.

Critical

Wildcard developer trust in config.runtime.py (covered in summary).
Workflow executor bypasses confirmation (covered).
browser_get has no SSRF protection — tools/builtin/browser_get.py hands any URL to Playwright page.goto(); injection → http://127.0.0.1:8001 (the llama server) or http://169.254.169.254 (cloud metadata). Same gap in web/browser_stream.py SessionStreamManager.start. Fix: reuse http_get._assert_ip_allowed.
Web bound to 0.0.0.0 (covered).
High

WebSocket admin bypass when user_id is None — browser_sessions.py browser_stream_ws.
Webhook secrets leak via GET /api/workflows — workflows.py list_workflows returns full trigger_config (including secret) with no ownership check; any authenticated user can harvest HMAC secrets and forge webhook triggers.
User.trust_preset / role is stored but never enforced — policy/default.py _trust_for() reads only HestiaConfig.trust + the trust_overrides dict. The docs and the AdminUsers UI imply per-user trust works; it does not. A "child" identity gets the owner's full tool surface.
Per-user trust is keyed on room/chat, not sender — Matrix passes sender_platform_user=None and keys the session on room_id; Telegram groups key on chat.id. Any member of an allowed Matrix room can drive the agent with shared trust.
Confirmation buttons aren't bound to the requester — in a group, anyone can approve someone else's pending email_send/terminal.
Medium: unauthenticated /api/auth/available-users enables user enumeration + OTP spam (rate limit is per-IP, 3/5min — weak); in-memory sessions (lost on restart, 72h lifetime, no revocation); email SMTP header injection in create_draft (to/subject not stripped of \r\n); http_get loads full body before truncation (multi-GB DoS); DNS-rebinding gap acknowledged in the SSRF transport; browser cookies stored plaintext; several diagnostic routes (/api/doctor, /api/audit, /api/config, /api/tools, /api/egress) lack require_admin; traces/egress/memory routes return unscoped global data when the caller identity is unresolved.

Low/nit: terminal uses create_subprocess_shell with a regex blocklist explicitly documented as not a boundary; no CORS/CSP/security-headers middleware; debug_login endpoint exists (off in runtime); webhook replay cache is per-process.

Architecture & abstractions
Honest verdict from both architecture passes: good-to-mediocre, and trending the right way. The orchestrator's assembly → execution → finalization split, the PolicyEngine ABC, the meta-tool pattern, the commands/ extraction, and run_platform() deduplication are deliberate, clean design. The strain shows in a handful of files that outgrew their abstractions and in a few places where two parallel models exist for one concept.

High — where it will hurt as you grow

persistence/sessions.py (1044 lines, ~32 methods) is the "everything store" — sessions + messages + turns + transitions + handoffs + slot fields + analytics, and it imports orchestrator.types (persistence depending upward on the domain layer). This is the clearest "split me" file. Fix: SessionStore / MessageStore / TurnStore, with persistence-local DTOs mapped to Turn only at the orchestrator boundary, and a HandoffService for the handoff business logic.
orchestrator/execution.py (1156 lines) — cohesive (one job) but too big; extract streaming reassembly, the circuit-breaker/tool-dispatch block, and meta-tool routing; leave run() a thin loop.
Workflows depend on the full AppContext (workflows/nodes/*.py, executor.py) — feature subsystems shouldn't import the composition root; inject a narrow WorkflowRuntime(inference, tool_registry, event_bus, notifier, trust) so nodes are testable without booting all of Hestia.
Duplicate DDL / schema drift — style_profiles and failure_bundles are declared in both schema.py and their stores' create_table(); proposals/memory live outside schema.py; skills is in Alembic only; error_resolutions is in Alembic but not the bootstrap path. trace_store.py even documents past pain from this. Consolidate to one schema owner.
Two parallel trust models — workflows/executor.py defines its own _TRUST_CAPS separate from TrustConfig + policy/default.py. One CapabilityGate should serve both (this is also the security finding above).
telegram_adapter.py (821 lines) vs matrix (353) — extract voice/streaming/markdown/confirmation submodules.
Medium: config.py (847 lines) carries both the new nested CoreConfig/PlatformConfig/FeatureConfig model and ~170–240 lines of deprecated flat aliases — transitional sprawl, pick one and codemod; app.py register_tools() is an 80-line imperative manifest (move to register_builtin_tools(app) colocated with the tools); WebContext duplicates store refs from AppContext; web routes hand-roll dict[str, Any] responses inconsistently (Pydantic on some, ad-hoc on others) — exposes internal shapes and drifts from the frontend; stringly-typed EventBus with payload: Any; CLI/web duplicate validation that should live in a shared service layer.

Dead/parallel code worth deleting: context/memory_epoch.py MemoryEpochBuilder (production uses memory/epochs.py), memory/session_summarizer.py (tests but no wiring), and the job-board URL heuristics (_JOB_URL_PATTERNS, _extract_best_job_url) embedded in the generic workflows/executor.py — that's personal domain logic in a supposedly generic engine and should move to a node helper.

What's genuinely good and shouldn't be over-engineered: the Platform ABC (keep it minimal), the EventBus/TriggerRegistry (don't reach for a real broker), CheckpointManager, and the meta-tool indirection (the token savings justify it). Hygiene is excellent: zero TODO/FIXME in src/, only ~12 type: ignore.

Code style & tooling health
mypy is not clean: 31 errors / 11 files (union-attr, arg-type, attr-defined). For a project that lists mypy as a quality gate, this should be zero. Notable: telegram_adapter.py:591 Chat | None has no .title; runners.py:127 passes VoiceConfig | None where VoiceConfig is expected.
ruff: 161 issues, dominated by 97 × E501 (line length) and 18 × E402 (import position). Mostly cosmetic debt, but it means the lint gate is being run with a large baseline rather than clean.
No py.typed marker despite docs implying typed-package status.
~30 broad except Exception (# noqa: BLE001) at platform/scheduler boundaries — intentional and commented, but inner handling is inconsistent.
Test layout is split: 119 flat tests/unit/test_*.py vs 32 nested mirroring src/ — finding the tests for a given module is harder than it should be.
Documentation
Grade: C+ — strong internals, weak front door. Subsystem guides (workflows, browser sessions, multi-user, voice, web-dashboard usage) and the 39 ADRs are solid and current. The entry layer contradicts the code.

README Quick Start is wrong — pip install hestia (no PyPI), --config config.py (no such file in the repo; only deploy/example_config.py), no mention of uv, llama.cpp, init, or that web.enabled defaults False. (Critical)
UPGRADE.md stops at v0.10.0 (project is 0.13.0; pyproject.toml itself says 0.12.2 — even the version numbers disagree across tag/changelog/pyproject). It also documents hestia skills and hestia memory epochs commands that don't exist, and links two guide files that don't exist. (Critical/High)
README tool names are wrong — rollback vs actual rollback_turn, proposal_accept vs accept_proposal, scheduler_add vs create_scheduled_task, style_reset vs reset_style_profile, etc. Anyone cross-referencing list_tools will be misled. (High)
SECURITY.md promises "responsible disclosure" but contains no disclosure process, contact, or supported-versions (CHANGELOG claims this was added in 0.7.x — it's gone now). (Critical)
Three contradictory migration stories — deploy/README.md says alembic upgrade head, persistence/migrations/__init__.py says "Hestia does not use Alembic," and the app actually bootstraps via create_tables() + runtime migrations. (High)
Architecture tree in README omits workflows/, events/, memory/, tools/browser/, audit/; the design/ doc still says "Matrix in progress, 311 tests, Phase 6"; deploy/example_config.py only covers Telegram+inference (can't enable web/matrix/email/browser); 205 dev-process files dwarf the 13 operator guides.
No public API docs — create_web_app() sets docs_url=None; web-ui/src/api/client.ts is the de-facto contract.
Top 3 doc investments: one authoritative Getting Started (clone → uv sync → init → llama.cpp → serve), bring UPGRADE + SECURITY current, and an accuracy pass on tool names / version / migration story.

Web UI — code quality
Health: B− — solid early-stage admin UI, not yet production-hardened. It passes its own AGENTS.md rule (12 inline style={{}}, under the 20 limit). Strict TS, a coherent CSS-token system, centralized copy (lib/text.ts), meaningful Vitest + Playwright tests, and sound 401/token wiring. Verified separately: 33 : any/as any, 2 console.log (both in BrowserStream.tsx), no ESLint configured.

High

useWorkflowEditor.ts (512 lines, 50+ returned fields) is a god-hook — graph + versions + triggers + executions + shortcuts + undo/redo in one. Returns a fresh object literal each render, so WorkflowEditor's [editor]-dependent callbacks (onNodesChange, onConnect) are recreated every render → ReactFlow churn. Split into focused sub-hooks; stabilize callbacks.
Modal markup is copy-pasted ~10 times with no Modal.tsx/ConfirmDialog component (the CSS exists, the component doesn't). Biggest ROI refactor.
No client-side token refresh; 401 clears token but doesn't throw — expired sessions can fail opaquely before a later json() parse.
Medium

Monolithic api/client.ts (703 lines) mixing all domains, with inconsistent error handling (checkOk vs bare !res.ok) and weak typing on many endpoints (fetchSessions, fetchProposals, fetchMemories, fetchConfig return bare res.json()), prompting call sites to re-declare types and drift.
useApiQuery's key is cosmetic — no cache/dedup/invalidation, so navigating away and back refetches, and useCurrentUser is fetched by both App and child pages.
Split fetch patterns — ~6 pages use useApiQuery, ~8 still hand-roll useEffect+loading/error; useApiMutation and useCurrentUser lack unmount guards (the useApiQuery race guard is good, though).
AbortController created but never wired to fetches in useWorkflowEditor (only a stale flag).
Low/dead code: ContextLab.tsx (unrouted), ProposalCard.tsx (unused — and it has the defer/evidence UX that Proposals.tsx reimplemented without), FormField.tsx (unused), t() helper in text.ts (unused), several unused API exports; key={idx} on session messages; duplicate User/Proposal interfaces; Knowledge.tsx uses window.location.href (full reload) instead of useNavigate; retries are mostly window.location.reload().

Top refactors: extract Modal/ConfirmDialog, split + type api/client.ts, standardize on useApiQuery (or adopt TanStack Query), decompose useWorkflowEditor, delete/wire the dead code, add ESLint with react-hooks/exhaustive-deps.

Web UI — UX
Both passes agree: a collection of capable admin screens, not yet one coherent product. Coherence score ~6/10 as a control panel, ~4/10 as a guided experience. The newer pages (Scheduler, AdminUsers, ErrorDashboard, BrowserSessions, Login) are reference-quality with EmptyState/skeleton/toasts/confirm-modals; the older ones (Workflows, Config, Proposals, Dashboard metrics) lag behind, so the app feels like three products stitched together.

Critical/High

Dashboard "Recent Sessions" actually shows workflow execution count (Dashboard.tsx:121) — misleads on the landing page.
ContextLab is fully built but unreachable (no route in App.tsx).
No nav path to chat sessions — /sessions/:id is reachable only from Knowledge (via a full-page window.location.href); there's no Sessions list and no Chat surface at all (conversation lives on Telegram/Matrix/CLI — the web UI only reads transcripts).
Flat 12-item nav with no grouping (Activity / Automation / Account / System / Admin).
Inconsistent feedback — toasts exist globally but aren't used on Proposals, Workflows, Profile, or trigger-save; deletes are a lottery of confirm-modal vs window.confirm; the workflow node delete (also bound to the Delete key) has no confirmation.
Modals lack role="dialog", focus trap, and Escape handling.
Medium: Workflows and Knowledge tables aren't responsive (responsive-table missing) — bad on the phone the owner actually uses; the Button component with its loading state is barely adopted; Style is duplicated between its own page and Knowledge; dashboard stat cards aren't clickable; workflow editor exposes raw tool_call/llm_decision node names and two confusing save paths (graph vs trigger); no graph validation before save/activate; ErrorDashboard doesn't deep-link to the failing workflow/session; dark-mode contrast risk from hardcoded light hex in some badges/turn states.

Highest-payoff UX fixes: fix the dashboard label + add a Sessions nav entry, group the nav, wire (or delete) ContextLab, standardize toasts + confirm modals, and bring Workflows/Config up to the Scheduler-quality pattern.

Big-picture read
Stepping back from the line items: this is a genuinely impressive solo/small-team project, and it is more ambitious than it is mature. The core bet — a local-first, tool-calling assistant engineered specifically around the failure modes of a small quantized model — is sound, and the execution of that bet is the best part of the codebase. The orchestrator's defensive machinery (JSON repair, XML fallbacks, circuit breakers, quality corrections, meta-tools to keep the tool catalog out of the prompt) is not generic LangChain-style plumbing; it's clearly the product of someone watching a 3060-class model misbehave over and over and hardening against it. That hard-won, domain-specific competence is the thing worth protecting. The orchestrator decomposition, the policy engine, and the capability-label system are good bones.

What concerns me is that the project has grown outward (features) faster than it has grown upward (the abstractions and invariants that keep features safe). The breadth is striking — CLI, Telegram, Matrix, email, voice, web dashboard, workflow DAG editor, browser automation with live streaming, reflection loop, style profiles, multi-user trust, memory epochs. But the two load-bearing invariants you'd want under all of that are the ones most clearly missing: a single enforced trust/capability boundary (right now it's split between the policy engine, the workflow executor's parallel _TRUST_CAPS, an unenforced per-user trust_preset, and a runtime config that throws the doors open with ["*"]), and a concurrency model (there is no per-session serialization anywhere, despite three independent things — users, scheduler, delegation — all able to drive the same session). Those aren't feature gaps; they're the structural assumptions that everything else quietly depends on, and they're soft. The same shape recurs in persistence: three different ways to create a table, a 1000-line store that reaches up into the orchestrator's domain types. None of this is fatal, but it's the kind of debt that turns a "add a feature" task into a "why did the database drift / why did two turns corrupt the slot" debugging session six months from now.

The security posture deserves a blunt framing: Hestia currently trusts its own LLM as if it were the operator, and it runs unattended. For a single-user CLI box that's a defensible tradeoff. But the project ships email polling, group-chat access, and webhooks — all untrusted-input channels — into the same tool-executing agent with wildcard auto-approve and a non-blocking injection scanner. The gap between the threat model the docs imply (trust presets, egress audit, sandboxing) and what the runtime config actually does is wide. I don't think this is carelessness so much as the natural result of "developer trust" being convenient during a fast build; the danger is that the convenient setting is the one sitting in the deployed config file.

On direction: I'd gently challenge the web UI's identity. It has quietly become a large second product — a workflow IDE, a remote-browser console, a user-admin panel — and the reviews keep surfacing the same thing: it's an admin/control plane masquerading as an assistant, with no place to actually talk to Hestia. That's a fine thing to be, but it should decide to be that. Right now effort is spread evenly across twelve screens of uneven maturity instead of concentrated on the two things that are actually differentiated (the workflow editor and the browser-auth stream). The job-board URL heuristics baked into the generic workflow executor are a tell: the project occasionally hardcodes one user's specific needs into what's supposed to be general infrastructure, which is fine for a personal tool but works against the "framework" framing in the README.

What I'd reconsider at a high level: slow down feature breadth and spend one cycle on invariants and the front door. Concretely — lock down the trust model and make per-user trust real; add the session mutex; consolidate the schema; pick whether the web UI is a control panel or a client and commit; and fix the README/UPGRADE/SECURITY trio so the project is honestly approachable. None of that is glamorous and none of it adds a feature, but it's the difference between "an impressive personal project that works because one person knows where the bodies are buried" and "something a second person could safely run and contribute to." The foundation is good enough to be worth that investment — which is precisely why I'd make it now, before there are twenty features resting on the soft spots instead of ten.

All eight review subagents completed successfully; this synthesis combines their findings with my own verification of the test suite, type checker, linter, and the orchestrator/workflow/auth code paths.
