# Runtime Branch Review

**Date:** 2026-05-11  
**Branch:** `feature/workflow-builder-runtime` (at `10a69ec`)  
**Delta from:** `feature/workflow-builder`  
**Scope:** ~3,555 additions, 612 deletions across 58 files  
**Loops covered:** L157 (browser session persistence), L158–L162 (memory/context/tool-exposure), L163 (inference hardening), plus runtime patches

---

## Executive Summary

This branch is the production runtime — the code that actually runs on Dylan's Linux box via `hestia-serve.service`. It layers ~30 commits on top of the workflow-builder feature branch, covering six areas: inference resilience against the Qwen3.5-9B model's quirks, cross-session conversation continuity via handoff records, memory epoch injection into system prompts, direct tool exposure (bypassing the `call_tool` wrapper), browser session persistence, and a Bing search engine swap after DuckDuckGo went fully CAPTCHA-gated.

The work is motivated by a concrete, well-documented struggle: the 9B reasoning model reliably fetches and parses data but exhausts its output token budget in reasoning before emitting tool calls, making multi-step autonomous workflows (like job board scraping) unreliable. Nine prompt iterations are documented with clear analysis of what worked and what didn't. The runtime patches are pragmatic responses to real operational failures.

**What works well:** The inference hardening is thorough and well-structured — three XML tool-call fallback formats, call_tool wrapper unwrapping, graceful malformed JSON handling, and streaming path parity. The session handoff design is clean. The context builder's system-message filtering prevents a real Qwen template crash. The circuit breaker for repeated empty-arg tool failures is a good operational pattern.

**What needs attention:** The execution.py file has a massive code duplication problem (~70 lines copy-pasted for the `finish_reason=stop + tool_calls` path). Several files were committed that shouldn't be in the repo. The session summarizer has no guard against summarizing with a model that can't reliably emit structured output. The `allowed_roots` config is hardcoded to a single job-search directory. And the fundamental model limitation remains unresolved — the review closes with architectural recommendations.

---

## Critical Issues

### CRIT-1: Massive code duplication in execution.py (lines 118–188 vs 196–257)

The `finish_reason == "stop"` branch that detects tool_calls duplicates the entire `finish_reason == "tool_calls"` branch — roughly 70 lines of identical logic including tool dispatch, delegation check, context rebuild, reasoning display, and iteration tracking. This was clearly copy-pasted to handle the edge case where llama-server returns `finish_reason=stop` alongside tool calls.

This is a maintenance hazard: any fix to one branch must be manually mirrored to the other. The comment on line 202 ("Re-use the tool_calls branch logic inline to avoid refactor") acknowledges this.

**Fix:** Extract a `_handle_tool_calls(ctx, turn, chat_response, transition, set_typing)` method and call it from both branches.

### CRIT-2: Session handoff injects system message that Qwen rejects

`get_or_create_session_with_handoff` (sessions.py:294-314) appends a synthetic `role="system"` message to the empty session. When `ContextBuilder.build()` later assembles the prompt, it creates its own system message and filters out system messages from history (line 247: `history = [msg for msg in history if msg.role != "system"]`).

The filtering works — which means the handoff data is silently discarded after the first turn. The handoff content survives only as long as it's in the initial history fetch before the builder strips it. This is correct behavior for preventing the Qwen crash, but it means the handoff is fragile: it only works on the very first build of the very first turn, and only because the builder hasn't seen the history yet at that point.

**Risk:** If the orchestrator ever pre-builds context before the first user message arrives (e.g., for warm-up), the handoff content would be stripped before it's ever seen. The handoff should use `role="user"` with a synthetic prefix like `[Previous session context]` instead.

### CRIT-3: Escape room planning file committed to repo

`escape_room_planning.md` is a personal file containing Dylan's family information (children's names, birth dates, ex-wife's name, travel plans). This should not be in a git repository, especially not one that might ever become public.

**Fix:** `git rm escape_room_planning.md` and add it to `.gitignore`.

### CRIT-4: `hestia-serve.service` duplicated at repo root

A systemd service file exists both at `deploy/hestia-serve.service` (canonical) and `hestia-serve.service` (root). The root copy appears to be accidental — it duplicates the deploy version. Having two copies means edits to one won't be reflected in the other.

**Fix:** `git rm hestia-serve.service` (keep only the `deploy/` copy).

---

## Security Issues

### SEC-1: `hestia-telegram.log` was tracked before gitignore fix

Commit `f1e9811` ("security: remove hestia-telegram.log from git tracking") and the `.gitignore` addition of `*.log` indicate that a log file containing potentially sensitive Telegram message content was previously tracked. The file is removed from tracking but may still exist in git history.

**Recommendation:** If this repo is ever shared or made public, the log file should be purged from history with `git filter-branch` or `git filter-repo`. For now, the `.gitignore` fix is sufficient.

### SEC-2: API key leak detection checklist added (good)

Commit `e03a872` adds an API key leak detection checklist to the self-review skill. This is a positive security practice and directly responds to SEC-1.

---

## Inference Hardening (L163 + runtime patches)

### What was done

The inference layer received the most attention on this branch, driven by real failures with the Qwen3.5-9B-DeepSeek-V4-Flash model:

1. **XML tool-call fallback** (`inference.py:36-182`): Three parsing formats — JSON in `<tool_call>` tags, ad-hoc `<function=name>` XML, and GLM-style `<arg_key>/<arg_value>` XML. This catches tool calls the model emits inside `<think>` blocks (reasoning_content) when it fails to produce structured `tool_calls` JSON.

2. **`call_tool` wrapper unwrapping** (`inference.py:108-123, 435-446`): Both the XML fallback and the structured path detect when the model wraps its real tool call inside `call_tool(name=X, arguments={...})` and unwrap to the inner tool. This handles models trained on the meta-tool pattern that can't be retrained.

3. **Malformed JSON graceful skip** (`inference.py:422-431`): Instead of crashing the turn on bad JSON in tool_call arguments, the turn continues with remaining valid tool calls. This is critical for the 9B model which produces ~50% malformed JSON in wrapper patterns.

4. **Streaming path parity** (`execution.py:300-408`): The streaming inference accumulator now has the same XML fallback as the non-streaming path (lines 379-396). Without this, streaming mode would silently drop tool calls that only appear in reasoning content.

5. **URL validation in XML fallback** (`inference.py:54-58`): Rejects URLs containing newlines, XML remnants, or truncation artifacts — prevents the model's half-formed tool calls from triggering real network requests.

6. **Empty-choices guard** (`inference.py:406-408`): Guards against `{"choices": []}` responses that previously caused IndexError.

### Assessment

This is solid defensive engineering. The three-format XML parser is well-structured with clear fallback ordering (JSON first, then ad-hoc XML, then GLM XML). The URL validation prevents a real attack vector where truncated XML could produce `browser_get` calls to garbage URLs.

**One concern:** The `_extract_tool_calls_from_text` function is 146 lines with three separate regex-heavy parsing paths. It would benefit from being split into three named functions (`_parse_json_tool_calls`, `_parse_adhoc_xml_tool_calls`, `_parse_glm_xml_tool_calls`) called in sequence, each returning early if it finds results.

**Another concern:** The `args` variable is reused across Format 2 and Format 3 (lines 92 and 153) with a `# noqa` implied by the re-binding. This is a minor readability issue but could mask bugs if the formats ever overlap.

---

## Session Continuity (L158–L162)

### L158: Auto-save session summary on archival

`memory/session_summarizer.py` sends the session's user/assistant dialogue to the inference client with `reasoning_budget=0` and a summarization prompt. The summary is stored in the handoff record.

**Concern:** This uses the same Qwen3.5-9B model that struggles with multi-step tasks. Summarization is a simpler task (no tool calls needed), but `reasoning_budget=0` may not be respected by all llama.cpp versions — some models emit reasoning regardless. If the model burns its token budget reasoning about the summary, the summary will be empty. The empty-string fallback is correct but means handoffs may silently degrade to key_messages-only.

### L159: Load memories into system prompt

`context/memory_epoch.py` fetches the 5 most recent memories (within 30 days, max 1500 chars) and prepends them to the system prompt. Clean implementation with proper error handling and truncation.

**Issue:** The `list_memories` call passes `platform` and `platform_user` but the MemoryStore's `list_memories` method may not filter by these fields (depends on implementation). If memories are global, all users see all memories. This needs verification against the actual MemoryStore implementation.

### L160: Subagent parent context inheritance

Not visible as a large change in this diff — likely a small parameter pass-through in the orchestrator. The concept is sound: subagents should see the parent's context to avoid redundant work.

### L161: Direct tool exposure

The model can now call tools directly (e.g., `browser_get(url=...)`) instead of going through `call_tool(name="browser_get", arguments={...})`. This is implemented via `parameters_schema` on all factory tools, which lets llama.cpp present them as native function-call options.

**This is the most impactful change on the branch.** The `call_tool` wrapper was the primary source of JSON malformation (~50% failure rate per the summary doc). Direct exposure eliminates the wrapper entirely for models that support native function calling.

The `call_tool` unwrapping in inference.py remains as a fallback for models that still use the wrapper pattern — good defense-in-depth.

### L162: Cross-session conversation continuity

`SessionHandoff` dataclass + `session_handoffs` table + migration `m002_session_handoffs`. When a session is archived, the last 8 user/assistant messages and any artifact handles are captured. The next session for the same user gets a synthetic system message with the handoff content.

**Design is clean** but see CRIT-2 above regarding the system-message role choice.

---

## Context Builder Improvements

The builder (`context/builder.py`) gained several important fixes:

1. **System message filtering** (line 247): Drops `role="system"` from history before assembly. This prevents the Qwen "System message must be at the beginning" crash when handoff injects a system message into the DB.

2. **Memory epoch and style prefix assembly** (lines 182-188, 248-251): Prefix layers are assembled in canonical order (identity → memory_epoch → style → system_prompt). This is well-structured.

3. **Batch tokenization** (`inference.py:267-327`): `tokenize_batch` joins texts with a unique separator, makes one HTTP call, then splits the token sequence. Falls back to individual calls if the separator appears in text or the split count is wrong. Good defensive implementation.

**Issue:** The `_count_body` method caches by `hash(tuple((m.role, m.content) for m in messages))` (line 377), but this cache is only used for single-message system prompts (line 406). The variable name `_last_system_cache_key` is misleading — it's guarding a much broader path. Not a bug, just confusing.

---

## Policy Changes

### Auto-delegation disabled (good)

`policy/default.py:125-128` comments out the `tool_chain_length > 5` auto-delegation trigger with the note: "DISABLED: auto-delegation is causing subagent loops with the 9B model." This is the right call — the 9B model can't reliably manage a single-step task, let alone coordinate a parent-child delegation.

The `projected_tool_calls > 3` trigger is also disabled (line 140). Keyword-based delegation ("delegate", "subagent", "research", "investigate") remains active. This is a pragmatic middle ground.

### Circuit breaker for empty-arg loops (execution.py:506-524)

After 3 consecutive calls to the same tool with empty/missing arguments that return "requires" or "missing" errors, the model gets a `🛑 CIRCUIT BREAKER` message telling it to stop. This prevents the infinite loop where the model keeps calling a tool without arguments and retrying on the error.

**This is excellent operational design.** The pattern is common with small models that understand "I need to call this tool" but can't construct the JSON payload.

---

## Search Engine Swap

`search_web.py` replaced DuckDuckGo with Bing HTML parsing via `curl_cffi` browser impersonation. Bing's redirect URLs are decoded from base64 (`a1` prefix → base64 decode). The implementation handles CAPTCHA detection, HTML tag stripping, deduplication, and snippet extraction.

**Assessment:** This is a pragmatic fix for a real operational failure (DuckDuckGo fully CAPTCHA'd all requests). The Bing HTML parser is fragile by nature — any Bing HTML redesign breaks it — but it's the right trade-off for a local-first system that avoids API keys.

**Issue:** The `curl_cffi` import is optional with a fallback to `http_get`, but `http_get` doesn't impersonate a browser and will likely also get CAPTCHA'd. The fallback is more of a "graceful degradation to failure" than a real fallback.

---

## Runtime Configuration

`config.runtime.py` is the production config file. Notable settings:

- **Model:** `Qwen3.5-9B-DeepSeek-V4-Flash-Q4_K_M.gguf` — the Q4 quantization of the model discussed in the prompt iteration summary
- **Context:** 32768 tokens (comment says 16384 per slot but value is 32768 — mismatch worth verifying against actual llama-server config)
- **Trust:** `developer` preset with wildcard auto-approve — no confirmation prompts for any tool
- **Allowed roots:** `["/home/<user>/Documents/Job Search"]` — very narrow sandboxing, likely temporary for the job search task
- **Max iterations:** 40 — extremely high; most turns should complete in 3–5 iterations. This was likely raised to give the model more attempts at the job scraping task.
- **System prompt:** 10 rules + tool examples, heavily tuned to combat specific model failure modes (CAPTCHA retry loops, curl fallback, infinite searching, empty JSON payloads)

**Observation:** The system prompt (lines 163-182) reads like a battle log of every failure mode encountered during the 9 prompt iterations. Rules 5-9 are all "STOP doing X" directives. This is characteristic of prompt engineering against a model at the edge of its capability — each rule is a scar from a specific failure. It works but is fragile; any new failure mode requires another rule.

---

## Files That Shouldn't Be in the Repo

| File | Issue |
|------|-------|
| `escape_room_planning.md` | Personal family information (children, ex-wife, travel plans) |
| `hestia-serve.service` (root) | Duplicate of `deploy/hestia-serve.service` |
| `config.runtime.py` | Contains email address (`agent@example.com`), hardcoded paths. Should be gitignored or use env vars exclusively |

`config.runtime.py` is borderline — it's useful as a reference config, but it contains operational details that tie it to a specific deployment. Consider a `config.runtime.example.py` pattern.

---

## The Model Problem — Architectural Assessment

The prompt iteration summary documents a thorough, methodical attempt to make the Qwen3.5-9B model perform autonomous multi-step extraction. The diagnosis is correct: this is a reasoning-first model that burns its output budget analyzing data instead of acting on it. The fundamental mismatch is:

1. **Model wants to reason** → generates 2,000–3,500 chars of analysis per turn
2. **Task needs action** → append_to_file calls require maybe 200 chars
3. **Budget is finite** → reasoning consumes the budget, action never happens
4. **Retry makes it worse** → on retry, the model reasons about why it failed to act, consuming even more budget

The four recommended paths in the summary (composite tool, non-reasoning model, human-in-the-loop, standalone scraper) are all valid. My assessment of priority:

**Path D (standalone scraper) is the right answer for job board scraping specifically.** The parsing rules are fully documented in `job-board-guide.md`. A 50-line Python script with `curl_cffi` and regex would be more reliable than any LLM-based approach for this structured extraction task. The LLM adds no value when the parsing rules are already known.

**Path A (composite tool) is the right answer for making the model generally more capable.** Wrapping multi-step sequences into single tools reduces the action surface the model needs to navigate. This is the same pattern that made direct tool exposure (L161) successful — fewer steps = fewer opportunities for reasoning overflow.

**Path B (non-reasoning model) is worth exploring** but the evaluation table shows 0 jobs from every alternative model tested. The issue may not be reasoning vs. non-reasoning but rather model size — 9B parameters may simply be too small for reliable agentic behavior with unstructured web data.

**Path C (human-in-the-loop) is already the de facto approach** — the 15 jobs were manually extracted. Formalizing this as a "model proposes, human confirms" workflow would be an honest acknowledgment of the current capability boundary.

---

## Copilot Findings (Cross-Referenced)

A separate copilot review surfaced additional issues, primarily on the web UI and workflow builder side of the runtime branch. These are integrated here with my assessment of each.

### Confirmed — Fix Before Release

**COP-1: `/api/tools` route missing but UI calls it.** `web-ui/src/api/client.ts` has a `fetchTools()` function, but no matching FastAPI route exists under `src/hestia/web/routes/`. This means tool dropdowns in ToolCallNode and InvestigateNode silently return empty lists. The L150 spec (constrained inputs) assumed this endpoint would exist — it was never built. This is a real usability gap: users can't select tools from a list and must type tool names freehand.

**COP-2: `"default"` node type addable but not executable.** The UI allows adding nodes with `type: "default"`, but the executor has no handler for it — it would fall through to tool invocation by node type and fail. The add-node menu should not expose this type.

**COP-3: Template interpolation promised but not implemented.** The UI suggests `{{node_id.field}}` patterns and previews templated strings in LLMDecisionNode and SendMessageNode. The backend passes raw strings with no interpolation engine. Users see placeholder syntax that does nothing. This is misleading and should either be implemented or the UI hints removed.

**COP-4: Workflow status color mapping bug.** The workflows page maps failure color to status `"error"` but the backend uses `"failed"`. Failed runs render with neutral styling instead of red/error indicators.

**COP-5: Trust level validation gap.** `update_workflow` validates trust levels but `create_workflow` does not. Invalid trust values can be persisted on creation. One-line fix — add the same validation to the create path.

### Confirmed — Security Polish

**COP-6: Webhook replay protection.** HMAC-only validation with no timestamp or nonce. Acceptable for v1 (the L148 spec acknowledged this as a known limitation) but should be documented and tracked for later hardening.

**COP-7: Auth manager encapsulation.** Web auth routes directly access `_code_request_limits` and `_is_rate_limited` — private-prefixed attributes on the auth manager. Works but brittle; a public `is_rate_limited(user)` method would be cleaner.

**COP-8: Session tokens in `sessionStorage`.** Fine for the local dashboard (which is behind 2FA anyway), but becomes XSS-sensitive if the dashboard is ever exposed beyond localhost. Worth noting in deployment docs.

### Confirmed — Architecture Strain

The copilot flagged four files that have grown too large and conflate too many responsibilities:

- `useWorkflowEditor.ts` — state, side effects, keyboard handling, save/activate/test, history, trigger config all in one hook
- `workflows.py` route file — CRUD, versions, webhooks, test-run, dashboard queries
- `orchestrator/execution.py` — duplicated tool-execution branches (same as my CRIT-1)
- `web-ui/src/api/client.ts` — monolithic transport + domain client

These map to existing loop specs: L152 (decompose WorkflowEditor), L154 (backend hardening). The route file split should be added — L154 or a new loop should extract webhook routes into their own file.

### Confirmed — Performance Observations

- **Workflow executor edge scanning** is O(V·E) per execution — fine at current scale (workflows with <20 nodes) but worth noting for future optimization.
- **Trigger dispatch full scan** on every event — TriggerRegistry does an in-memory scan of all workflows per event. L147's `reload()` fix addresses staleness but not scan efficiency. A topic-keyed index would help at scale.
- **browser_get launches fresh Chromium per call** — robust isolation but expensive for repeated scraping loops. A connection-pooled approach (keep browser alive across calls within a turn) would be a significant performance improvement for scraping workflows.
- **Inline styles in UI** — maintainability concern as the UI surface grows. Not blocking but should be addressed when the UI is next refactored.

### Copilot's Model Assessment — Agreement

The copilot's recommendations for the model problem align with mine. Ranked by feasibility:

1. **Site-specific composite tools** (strongest) — both reviews agree this is Path A and the best general-purpose improvement
2. **Planner/executor split** — the copilot suggests the model output only a small JSON plan that runtime executes deterministically. This is a good architectural direction that goes beyond my Path A recommendation — it separates planning (what the model is good at) from execution (what it's bad at)
3. **Action-forcing guardrails** — short-circuit if reasoning grows past threshold with no tool call. This is a new suggestion not in my review and worth implementing. The orchestrator could detect `reasoning_content` length > N with no tool calls and inject a "you must emit a tool call now" system message
4. **Tuned retry policy** — separate retry behavior for malformed tool payloads vs empty responses. Currently both hit the same `retry_after_error` path
5. **Scheduled deterministic scraper** — both reviews agree this is the right answer for job boards specifically

---

## Recommended Follow-Up

| Priority | Item | Covers |
|----------|------|--------|
| **Immediate** | Remove personal files from repo | CRIT-3, CRIT-4 |
| **Immediate** | Purge `hestia-telegram.log` from git history if repo will be shared | SEC-1 |
| **High** | Extract `_handle_tool_calls` method in execution.py | CRIT-1 |
| **High** | Change handoff message role from "system" to "user" | CRIT-2 |
| **High** | Add `/api/tools` endpoint (list registered tools with schemas) | COP-1 |
| **High** | Remove "default" from node type menu; fix workflow status color mapping | COP-2, COP-4 |
| **High** | Build standalone job scraper script (Path D) | Model limitation |
| **Medium** | Either implement `{{variable}}` interpolation or remove UI hints for it | COP-3 |
| **Medium** | Add trust level validation to `create_workflow` | COP-5 |
| **Medium** | Add reasoning-length guardrail (action-forcing short-circuit) | Copilot suggestion |
| **Medium** | Split `_extract_tool_calls_from_text` into three named parsers | Readability |
| **Medium** | Verify context_length 32768 matches actual llama-server config | Config |
| **Medium** | Verify MemoryStore.list_memories filters by platform/platform_user | L159 correctness |
| **Medium** | Add composite tools for common multi-step patterns (Path A) | Model capability |
| **Medium** | Extract webhook routes from `workflows.py` into own file | COP architecture |
| **Low** | Add `is_rate_limited()` public method to auth manager | COP-7 |
| **Low** | Template `config.runtime.py` → `config.runtime.example.py` | Repo hygiene |
| **Low** | Reduce `max_iterations` from 40 to a sane default (10–15) | Config |
| **Low** | Consider `reasoning_budget=512` or lower for summarization calls | L158 reliability |

---

## What Looks Good

- The inference hardening is the strongest work on this branch — three fallback formats, wrapper unwrapping, URL validation, empty-choices guard, streaming parity. This is production-quality defensive engineering.
- The circuit breaker pattern for empty-arg loops is a genuinely good idea that other agent frameworks should steal.
- The session handoff design (table + migration + handoff record + builder filtering) is clean and well-thought-out.
- The prompt iteration summary is excellent documentation — honest about failures, precise about root causes, and actionable in its recommendations. This is how engineering journals should read.
- Direct tool exposure (L161) is the single most impactful change for model reliability. Eliminating the `call_tool` wrapper removes the primary source of JSON malformation.
- The migration system (idempotent, additive-only, dialect-portable) is the right approach for a project that doesn't need Alembic yet.
- The `SOUL.md` identity document is well-written — concise, practical, and personality-appropriate for a local-first assistant.
- Disabling auto-delegation was the correct operational decision for the current model capability.

---

*End of review.*
