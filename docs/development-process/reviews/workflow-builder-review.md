# Workflow Builder Feature Review

**Date:** 2026-05-02
**Branch:** `feature/workflow-builder` (at `be738a5`)
**Loops covered:** L134–L145 (Workflow data models through execution history)
**Scope:** 7,500 lines across 70 files

---

## Executive Summary

The workflow builder feature delivers a working React Flow editor, a backend DAG executor with six node types, an event bus with trigger registry, versioned workflow storage, and webhook support. The amount of ground covered is impressive for 12 loops.

However, there are two critical architecture bugs that undermine the core value proposition: the **executor does not gate downstream nodes on branching** (condition and LLM decision nodes execute ALL paths regardless of output), and **`await` on a sync `publish()` method** will TypeError at runtime for chat/message triggers. Beyond those, the webhook endpoint has no authentication, the condition node's expression evaluator has a sandbox escape via dunder attributes, and the UI is missing several fundamental interactions (no delete, no node deletion, no undo, branching nodes only have single output handles).

---

## Critical Bugs

### CRIT-1: DAG executor does not implement branching

**File:** `src/hestia/workflows/executor.py:217-288`

The executor topologically sorts all nodes and executes every one unconditionally. When a condition node evaluates to `False` or an LLM decision node selects branch "A", nodes on the other branches still execute. Edge `condition` fields and source handles are never evaluated to gate execution.

This defeats the core purpose of having condition and LLM decision nodes. A workflow with "if error → notify, else → continue" will always notify AND continue.

**Fix:** After executing a branching node, only enqueue successors whose edge `source_handle` or `condition` matches the node's output. Skip nodes with no path from an active branch.

### CRIT-2: `await` on sync `EventBus.publish()` — runtime TypeError

**Files:** `src/hestia/platforms/runners.py:184,194`, `src/hestia/events/bus.py`

`EventBus.publish()` is a synchronous method returning `None`. But `runners.py` calls `await app.event_bus.publish(...)` in two places. This will raise `TypeError: object NoneType can't be used in 'await' expression` at runtime, meaning `chat_command` and `message_matched` triggers never fire from Telegram/Matrix.

The webhook route correctly calls `publish()` without `await`.

**Fix:** Make `EventBus.publish()` async, or remove `await` in runners.py.

### CRIT-3: Condition node sandbox escape via dunder attributes

**File:** `src/hestia/workflows/nodes/condition.py:138`

`_eval_node` for `ast.Attribute` calls `getattr(obj, node.attr)` with no restriction. An expression like `x.__class__.__bases__[0].__subclasses__()` can traverse the Python object graph and access arbitrary classes. The existing test for `__import__('os')` only blocks `Call` nodes — attribute traversal is unrestricted.

**Fix:** Deny any attribute starting with `_` in the evaluator.

### CRIT-4: Condition node `operator.pow` allows resource exhaustion

**File:** `src/hestia/workflows/nodes/condition.py:73`

`ast.Pow: operator.pow` with no bounds. Expression `10 ** 10 ** 10` will consume unbounded memory/CPU.

**Fix:** Remove Pow from allowed operators, or impose magnitude limits.

---

## Security Issues

### SEC-1: Webhook endpoint has no authentication

**File:** `src/hestia/web/routes/workflows.py:245-275`

`POST /api/webhooks/{endpoint}` accepts arbitrary requests with no HMAC signature, no shared secret, no rate limiting. Any process on localhost (or the network if bound to 0.0.0.0) can trigger arbitrary workflow executions.

**Fix:** Require a per-workflow webhook secret in `trigger_config`. Validate `X-Webhook-Signature` header (HMAC-SHA256 of body with that secret). Return 401 on mismatch.

---

## Backend Issues

### BE-1: TriggerRegistry uses stale in-memory workflow list

**File:** `src/hestia/workflows/triggers.py:52-65`

`start()` loads all workflows once. Workflows created/updated/deleted via the API afterward are never reflected. New workflows never fire; deleted ones remain active.

**Fix:** Add a `reload()` method called after workflow CRUD operations, or query the store on each event with a short TTL cache.

### BE-2: `create_workflow` doesn't set owner or trust level

**File:** `src/hestia/web/routes/workflows.py:84-102`

Workflows are created with empty `owner_id` and default `"paranoid"` trust level. No route allows updating these. Workflows needing capabilities above paranoid can never be properly configured via the API.

### BE-3: Node capabilities not serialized to API

**File:** `src/hestia/web/routes/workflows.py:41-48`

`_version_to_api` does not include node `capabilities` in the response, and `create_version` never reads them from the payload. Trust enforcement uses capabilities but there's no way to set or inspect them via the API.

### BE-4: No `limit` validation on list_executions

**File:** `src/hestia/web/routes/workflows.py:281`

`limit: int = 50` with no upper bound. `?limit=999999999` loads the entire table.

### BE-5: Event bus tasks are fire-and-forget

**File:** `src/hestia/events/bus.py:49`

`asyncio.create_task` without storing references — tasks can be garbage-collected before completion.

### BE-6: InvestigateNode leaks upstream data

**File:** `src/hestia/workflows/nodes/investigate.py:53`

Passes the full `inputs` dict to every tool, potentially leaking sensitive data from upstream nodes to tools that shouldn't see it.

---

## UI/UX — Missing CRUD Operations

### UX-1: No delete workflow

Backend `DELETE /workflows/{id}` exists. The UI has no delete button, and `client.ts` has no `deleteWorkflow()` function. Users cannot remove workflows.

### UX-2: No node deletion

Once a node is added to the canvas, there is no way to remove it. No delete button in the properties panel, no keyboard Delete key handling, no right-click context menu.

### UX-3: No workflow rename

The editor shows the workflow name as a static `<h2>`. The `updateWorkflow` API exists but the UI never calls it for renaming.

### UX-4: No workflow duplication

No clone/duplicate operation in backend or frontend.

### UX-5: Version management is invisible

The `versions` state is fetched but the value is discarded (destructured as `[, setVersions]`). Users cannot browse, select, compare, or roll back versions. "Activate Version" always activates the latest save.

---

## UI/UX — Input Types

### UX-6: Free-text inputs that should be constrained

| Field | Current | Should Be |
|-------|---------|-----------|
| Tool Name (ToolCallNode) | Free text `<input>` | Dropdown of registered tools from `/api/tools` |
| Platform (SendMessageNode) | Free text `<input>` | Dropdown of configured adapters |
| Investigate "Tools" | Comma-separated text | Multi-select of available tools |
| LLM Decision "Branches" | Comma-separated text | Tag chips with add/remove |
| Condition Expression | Single-line `<input>` | Textarea with syntax help |
| Target User (SendMessage) | Free text | Autocomplete from known users |

HTTP Method in HttpRequestNode is already a `<select>` — that's the one field done right.

### UX-7: Cron input is a bare textbox

The schedule trigger renders `<input placeholder="Cron expression">` with:
- No validation of cron syntax
- No human-readable preview ("Runs every Monday at 8:00 AM")
- No presets for common intervals
- No timezone selector

---

## UI/UX — Missing Triggers

### UX-8: No email trigger

Current triggers: `manual`, `schedule`, `chat_command`, `message`, `webhook`. There is no `email_received` trigger type despite email being a configured platform adapter.

### UX-9: No internal event triggers

No triggers for system events like "proposal approved", "tool error", "new session started", or "workflow A completed".

---

## UI/UX — Editor Experience

### UX-10: Branching nodes have single output handles

Condition and LLM Decision node components each render a single bottom `<Handle>`. There are no separate true/false handles for conditions or per-branch handles for LLM decisions. The visual graph cannot represent conditional paths — which is the whole point of these nodes.

This is the UI manifestation of CRIT-1 (executor doesn't branch either). Both the backend logic and the frontend visualization need to support multi-handle branching.

### UX-11: No undo/redo

No history stack, no Ctrl+Z/Ctrl+Y support. Standard expectation for any visual editor.

### UX-12: No unsaved-changes protection

No dirty state tracking. Users can navigate away and lose all work without warning.

### UX-13: No confirmation dialogs

Zero confirmation prompts for any action — no confirm on activating a version, test running (which executes real side effects for LLM nodes), or any future delete operations.

### UX-14: Random node placement

New nodes are placed at `Math.random() * 200 + 50`. No auto-layout, snap-to-grid, or alignment guides.

### UX-15: No empty canvas guidance

New workflows show a blank canvas with no hint like "Drag to add your first node" or "Click + to add a node."

### UX-16: No keyboard shortcuts

No Ctrl+S to save, no Delete key, no Ctrl+Z undo, no Escape to deselect.

---

## UI/UX — Node-Specific Issues

### UX-17: LLM Decision — no variable interpolation

The prompt textarea has no indication of how to reference upstream node outputs. No `{{variable}}` syntax documentation or autocomplete.

### UX-18: Condition — no expression documentation

No documentation on expression syntax. Users don't know what language the expression uses, what variables are available, or what operators are supported.

### UX-19: HttpRequest — silent JSON parse failure

Headers JSON textarea uses `onBlur` with silent `catch {}`. Invalid JSON is accepted with no error message.

### UX-20: HttpRequest — missing methods

No PATCH or HEAD in the method select.

### UX-21: SendMessage — no template preview

No preview of what the rendered message will look like. No character count for platform limits.

---

## Test Coverage Gaps

### TST-1: No test for branching/gating in executor

Zero tests verify that condition=False or LLM selecting branch "A" prevents execution of nodes on other branches. This would immediately expose CRIT-1.

### TST-2: No test for dunder attribute access in condition node

The `__import__` test blocks at the `Call` level, not at attribute traversal. `x.__class__` would succeed.

### TST-3: No test for Pow exhaustion

No test for `10**10**10` or similar resource-exhaustion expressions.

### TST-4: No webhook authentication test

The only webhook test verifies that webhooks bypass session auth. No test for webhook-specific authentication.

### TST-5: Event bus tests use fragile timing

All tests rely on `asyncio.sleep(0.01)` instead of deterministic synchronization.

### TST-6: Executor test uses unconnected nodes

`test_node_failure_stops_execution` has nodes with no edges — execution order depends on sort insertion order, not actual dependencies.

---

## What Looks Good

- React Flow integration is clean — canvas, minimap, controls all work
- Workflow store versioning with partial unique index is correctly implemented
- HTTP request node uses SSRFSafeTransport (same protection as http_get tool)
- Execution history with per-node results is well-structured
- Event bus pub/sub pattern is simple and adequate
- Test coverage for store CRUD and individual node types is solid
- The investigate node concept (routing failures to chat) is a great differentiator

---

## Recommended Follow-Up Loops

| Loop | Title | Priority | Covers |
|------|-------|----------|--------|
| L146 | Executor branching + condition node security | Critical | CRIT-1, CRIT-3, CRIT-4, UX-10, TST-1-3 |
| L147 | EventBus async + trigger reload + SendMessage field mismatch | Critical | CRIT-2, BE-1, BE-5, + copilot SendMessage fix |
| L148 | Webhook authentication | High | SEC-1, TST-4 |
| L149 | Workflow CRUD completion (delete, rename, version UI, save/activate split) | High | UX-1, UX-2, UX-3, UX-5, + copilot handleSave fix |
| L150 | Constrained inputs + cron helper | Medium | UX-6, UX-7 |
| L151 | Email trigger + internal event triggers | Medium | UX-8, UX-9 |
| L152 | Editor UX (undo, dirty state, shortcuts, confirmations, decompose) | Medium | UX-11-16, + copilot WorkflowEditor decomposition |
| L153 | Node UX polish (expression docs, template preview, JSON validation) | Medium | UX-17-21, + copilot defaultValue/controlled textarea fix |
| L154 | Backend hardening (owner/trust, capabilities, N+1, limit, upsert, test payload) | Medium | BE-2, BE-3, BE-4, BE-6, + copilot N+1/upsert/_engine fixes |
| L155 | Editor navigation + dashboard | Medium | + copilot dashboard/breadcrumb/execution-labels findings |
| L156 | Test improvements (deterministic bus, connected DAG, branching edges, error states) | Medium | TST-4-6, + copilot err:any/node-placement fixes |
