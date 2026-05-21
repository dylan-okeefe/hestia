# L150 — Constrained Inputs and Cron Helper

**Status:** Spec only
**Branch:** `feature/l150-constrained-inputs-cron` (from `feature/workflow-builder`)
**Depends on:** L134

## Intent

Most node configuration inputs are free-text fields that should be constrained. Users are expected to type exact tool names, platform identifiers, and cron expressions from memory. This creates a high error rate at runtime — the node fails because the user typed "telegarm" instead of "telegram" or "get_weather" instead of "http_get". The scheduler trigger expects raw cron syntax with no validation, preview, or presets.

## Scope

### §1 — Tool name dropdown for ToolCallNode

In `web-ui/src/pages/WorkflowEditor.tsx` (properties panel, `tool_call` section):

1. Replace the free-text `<input>` for tool name with a `<select>` dropdown.
2. Fetch available tools from `GET /api/tools` on editor mount (this endpoint already returns the registered tool list).
3. Add a `fetchTools()` function to `client.ts` if not already present.
4. Populate the dropdown with tool names. Include a disabled "Select a tool…" placeholder option.

**Commit:** `feat(web-ui): tool name dropdown for ToolCallNode`

### §2 — Platform dropdown for SendMessageNode

In `web-ui/src/pages/WorkflowEditor.tsx` (properties panel, `send_message` section):

1. Replace the free-text platform `<input>` with a `<select>` dropdown.
2. Fetch configured platforms from `GET /api/auth/status` (which already returns `available_platforms`) or add a dedicated `GET /api/platforms` endpoint that returns running adapter names.
3. If adding a new endpoint, create it in `src/hestia/web/routes/workflows.py` or a new `platforms.py` router — return `["telegram", "matrix"]` (or whichever adapters are configured and running).

**Commit:** `feat(web-ui): platform dropdown for SendMessageNode`

### §3 — Multi-select for InvestigateNode tools

In `web-ui/src/pages/WorkflowEditor.tsx` (properties panel, `investigate` section):

1. Replace the comma-separated text input for "Tools" with a multi-select checkbox list.
2. Use the same tool list fetched in §1.
3. Store selected tools as an array in `node.data.tools` (serialize to comma-separated for backward compat with the backend, or update the backend to accept arrays).

**Commit:** `feat(web-ui): multi-select tool picker for InvestigateNode`

### §4 — Tag chips for LLM Decision branches

In `web-ui/src/pages/WorkflowEditor.tsx` (properties panel, `llm_decision` section):

1. Replace the comma-separated text input for "Branches" with a tag-chip component.
2. Render each branch as a removable chip/pill (text + "×" button).
3. Include an input field that adds a new chip on Enter or comma.
4. Store as an array in `node.data.branches`.

**Commit:** `feat(web-ui): tag chips for LLM Decision branch names`

### §5 — Cron expression helper for schedule trigger

In `web-ui/src/pages/WorkflowEditor.tsx` (trigger config panel, when `trigger_type == "schedule"`):

1. Keep the raw cron input but add:
   - **Validation on blur:** Parse the expression with a lightweight cron parser (use `cron-parser` npm package or a simple regex for 5-field cron). Show red border and error text for invalid syntax.
   - **Human-readable preview:** Below the input, display a natural-language description. Use `cronstrue` npm package (`npm install cronstrue`) which converts `"0 8 * * 1"` → `"At 08:00 AM, only on Monday"`.
   - **Preset buttons:** Add quick-select buttons for common intervals: "Every hour", "Every day at 8am", "Every Monday", "Every 5 minutes". Clicking fills the input.
2. Install `cronstrue` as a frontend dependency.

**Commit:** `feat(web-ui): cron expression helper with validation, preview, and presets`

### §6 — Textarea for condition expression

In `web-ui/src/pages/WorkflowEditor.tsx` (properties panel, `condition` section):

1. Replace the single-line `<input>` for expression with a `<textarea rows={3}>`.
2. Add a small help link or tooltip below: "Supported: comparisons (==, !=, <, >, <=, >=), logic (and, or, not), arithmetic (+, -, *, /), attribute access (data.field). No function calls or power operator."

**Commit:** `feat(web-ui): textarea with syntax help for condition expressions`

### §7 — Tests

1. **Tool dropdown test:** Mount editor with a tool_call node selected. Mock `/api/tools` to return `["http_get", "http_post"]`. Assert dropdown renders both options.
2. **Platform dropdown test:** Mock platforms endpoint. Assert dropdown shows "telegram" and "matrix".
3. **Cron validation test:** Enter invalid cron `"* * *"`. Assert error message appears. Enter valid `"0 8 * * 1"`. Assert human-readable preview shows "At 08:00 AM, only on Monday" (or similar).
4. **Tag chips test:** Add branch "route_a" via Enter key. Assert chip appears. Click × on chip. Assert removed.
5. **Multi-select test:** Check two tools in the InvestigateNode panel. Assert `node.data.tools` contains both.

**Commit:** `test(web-ui): constrained input component tests`

## Evaluation

- Tool names, platforms, and investigate tools are selectable from dropdowns/multi-selects (no free-typing of identifiers)
- Cron input validates syntax, shows human-readable description, and offers presets
- LLM Decision branches use tag chips instead of comma-separated text
- Condition expression has a multi-line textarea with syntax documentation
- All constrained inputs still serialize correctly to the backend

## Acceptance

- Frontend tests pass
- `mypy src/hestia` reports 0 new errors (if backend changes)
- `ruff check src/ tests/` clean on changed files
- `.kimi-done` includes `LOOP=L150`
