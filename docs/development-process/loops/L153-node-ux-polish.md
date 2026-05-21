# L153 — Node UX Polish

**Status:** Spec only
**Branch:** `feature/l153-node-ux-polish` (from `feature/workflow-builder`)
**Depends on:** L134, L150

## Intent

Individual node configuration panels have usability gaps that cause silent failures or confusion: condition expressions have no documentation of available syntax, the LLM decision prompt has no variable interpolation guidance, HTTP request headers silently swallow JSON parse errors, the method select is missing PATCH/HEAD, SendMessage has no template preview, and textarea inputs use `defaultValue` (uncontrolled) which causes React state/DOM divergence on re-renders.

## Scope

### §1 — Condition expression documentation

In `web-ui/src/components/workflow-editor/NodePropertiesPanel.tsx` (or inline in the condition section):

1. Below the condition expression textarea (from L150 §6), add a collapsible "Syntax Help" section.
2. Content:
   - **Variables:** `input.field_name` — access outputs from upstream nodes
   - **Comparisons:** `==`, `!=`, `<`, `>`, `<=`, `>=`
   - **Logic:** `and`, `or`, `not`
   - **Arithmetic:** `+`, `-`, `*`, `/` (no power operator)
   - **Literals:** strings in quotes, numbers, `True`, `False`, `None`
   - **Examples:** `input.status == "error"`, `input.count > 10 and input.retry`, `not input.skipped`
3. Default to collapsed to save space; persist open/closed in local component state.

**Commit:** `feat(web-ui): condition expression syntax documentation panel`

### §2 — LLM Decision variable interpolation

In the LLM Decision properties panel:

1. Above the prompt textarea, add a label: "Use `{{node_id.field}}` to reference upstream outputs."
2. Below the textarea, list available upstream node IDs and their types (derive from edges targeting this node, then look up those source nodes). Example: "Available: `start.output`, `condition_1.result`".
3. This is informational only — no autocomplete needed in this loop (that's a future nice-to-have).

**Commit:** `feat(web-ui): variable interpolation guidance for LLM Decision prompt`

### §3 — HTTP Request header validation

In the HTTP Request properties panel:

1. Replace silent `catch {}` on JSON parse with visible error feedback. On blur of the headers textarea:
   - Try `JSON.parse(value)`.
   - If invalid: set a red border, show error text below ("Invalid JSON — headers must be a JSON object like `{\"Authorization\": \"Bearer ...\"}`)").
   - If valid but not an object: show "Headers must be a JSON object, not an array or primitive."
   - If valid object: clear error, green border briefly.
2. Add `PATCH` and `HEAD` to the HTTP method `<select>` options (currently only GET, POST, PUT, DELETE).

**Commit:** `feat(web-ui): HTTP request header validation and PATCH/HEAD methods`

### §4 — SendMessage template preview

In the SendMessage properties panel:

1. Below the message textarea, add a "Preview" section that renders the message with variable placeholders highlighted (e.g., `{{node_id.field}}` shown in a colored pill/badge).
2. If no variables are used, just show the raw text.
3. Add a character count below the preview. Show a yellow warning at 4000 chars ("May exceed Telegram message limit") and red at 4096 ("Exceeds Telegram limit, will be truncated").

**Commit:** `feat(web-ui): SendMessage template preview with character count`

### §5 — Fix defaultValue textarea issue

In all node property panel textareas (Args JSON in ToolCallNode, Headers JSON in HttpRequestNode, Prompt in LLMDecisionNode):

1. Replace `defaultValue={...}` with `value={...}` (controlled component pattern).
2. This requires ensuring the `onChange` handler is always wired — which it already is in all cases. The `defaultValue` pattern causes the textarea to not update when the user selects a different node (React doesn't re-render uncontrolled inputs when key/value changes).
3. Verify by testing: select node A (has prompt "foo"), select node B (has prompt "bar"), assert textarea shows "bar" not "foo".

**Commit:** `fix(web-ui): use controlled value for all node config textareas`

### §6 — Execution history shows node labels

In `web-ui/src/pages/WorkflowEditor.tsx` (execution history panel):

1. Currently, `node_results` display raw `node_id` (UUIDs). Map each `node_id` to its `node.data.label` for display.
2. In the execution detail view, show: `"{label}" ({type}) — {status} — {elapsed_ms}ms` instead of just the node_id and status.
3. If a node_id doesn't match any current node (workflow was edited since execution), show the raw ID with "(deleted node)" suffix.

**Commit:** `feat(web-ui): execution history shows node labels instead of IDs`

### §7 — Tests

1. **Condition syntax help test:** Assert collapsible section renders, contains "==" and "and" examples, toggles on click.
2. **Variable interpolation test:** Mount LLM Decision panel with upstream nodes. Assert available variables are listed.
3. **Header validation test:** Enter `{invalid json`, blur, assert error message visible. Enter `{"a":"b"}`, blur, assert no error.
4. **Method select test:** Assert PATCH and HEAD are options in the HTTP method dropdown.
5. **Controlled textarea test:** Render panel with node A selected. Switch to node B. Assert textarea value updated.
6. **Execution label test:** Render execution history with node_results. Assert labels shown, not UUIDs.

**Commit:** `test(web-ui): node UX polish tests`

## Evaluation

- Condition node shows collapsible syntax documentation
- LLM Decision shows available variable references from upstream nodes
- HTTP Request headers validate on blur with clear error messaging
- PATCH and HEAD methods available
- SendMessage shows template preview and character count
- All textareas are controlled (no stale content on node switch)
- Execution history shows human-readable node labels

## Acceptance

- Frontend tests pass
- No TypeScript errors
- `.kimi-done` includes `LOOP=L153`
