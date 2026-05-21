# L174 — Workflow Editor UX Overhaul

**Status:** Spec only  
**Branch:** `feature/l174-workflow-editor-ux` (from `feature/l172-openui-foundation`)  
**Depends on:** L172 (OpenUI foundation and shared components)

## Intent

The workflow editor is the most complex page in Hestia and also the most problematic for usability. The review found: empty platform dropdowns, free-text inputs for known entities (users, tools), snake_case trigger and node type names, raw cron syntax with no builder, no tooltips, no way to reference trigger inputs, and raw JSON textareas with zero schema guidance. A non-developer cannot use this page.

This loop rebuilds the editor's property panels, trigger configuration, and node creation UI using the shared components from L172. The goal is not just cosmetic — it is to make the workflow model *discoverable*: a user should be able to build a workflow without reading source code.

## Scope

### §0 — Trigger configuration overhaul

**Why:** Trigger types display in snake_case with no human-readable labels. The schedule trigger expects raw cron syntax. The tool_error trigger uses a free-text tool name. These are the entry points to every workflow — if users can't configure triggers, they can't build workflows.

In `web-ui/src/pages/WorkflowEditor.tsx` (trigger config panel):

1. **Trigger type selector:**
   - Replace raw text or plain `<select>` with `TriggerTypeDropdown` from L172.
   - Show human-readable labels ("Chat Command", "Webhook", "Scheduled").
   - Add a one-sentence description below the dropdown explaining what the selected trigger does.

2. **Schedule trigger:**
   - Replace raw cron `<input>` with a builder component:
     - Frequency selector: "Hourly", "Daily", "Weekly", "Custom"
     - For Daily: time picker (hour + minute)
     - For Weekly: day-of-week checkboxes + time picker
     - For Custom: raw cron input with validation and `formatCron` preview
   - Preset buttons: "Every hour", "Every day at 8 AM", "Every Monday", "Every 5 minutes"
   - Human-readable preview below the input: "At 08:00 AM, only on Monday"
   - Validation on blur: red border + error text for invalid cron

3. **tool_error trigger:**
   - Replace free-text "Tool name" input with `ToolDropdown` from L172.
   - Include an "Any tool" option (empty string or `*`).

4. **chat_command trigger:**
   - Keep command text input but add placeholder: "e.g. weather, remind, status"
   - Helper text: "The word users type to activate this workflow."

5. **webhook trigger:**
   - Show the generated webhook URL as read-only copyable text
   - Helper text: "Send a POST request to this URL to trigger the workflow."

**Commit:** `feat(web-ui): rebuild trigger configuration with human-readable labels and cron builder`

### §1 — Node type and property panel overhaul

**Why:** Node types display in snake_case. Property panels use free-text for platforms, target users, and tool names. The Args (JSON) field is a blank textarea with zero guidance. Message preview shows "0 characters" with no guidance.

In `web-ui/src/pages/WorkflowEditor.tsx` (properties panel, per node type):

1. **Node type selector:**
   - Replace plain text with `NodeTypeDropdown` from L172.
   - Show human-readable labels ("Send Message", "Tool Call", "LLM Decision").

2. **Send Message node:**
   - Platform: `PlatformDropdown` instead of free-text
   - Target User: `UserDropdown` instead of free-text
   - Message body: `<textarea>` with character count and max-length hint
   - Message preview: render the actual message text with variable placeholders highlighted
   - Helper text: "Use {data.field_name} to reference trigger or upstream node outputs."

3. **Tool Call node:**
   - Tool name: `ToolDropdown` instead of free-text
   - Args (JSON): structured form instead of raw textarea
     - Fetch tool schema from `GET /api/tools/{name}` (if schema endpoint exists; otherwise keep textarea but add placeholder with example JSON)
     - If schema available: render labeled inputs per argument key
     - If no schema: textarea with placeholder showing example args for the selected tool
   - Helper text: "Arguments passed to the tool as a JSON object."

4. **LLM Decision node:**
   - Branches: tag-chip component (Enter to add, × to remove) instead of comma-separated text
   - Prompt: `<textarea rows={4}>` with character count

5. **Condition node:**
   - Expression: `<textarea rows={3}>` with syntax help link
   - Helper text: "Supported: ==, !=, <, >, and, or, not. Reference data with data.field_name."

6. **Investigate node:**
   - Tools: multi-select checkbox list from the tool registry instead of comma-separated text

**Commit:** `feat(web-ui): rebuild node property panels with constrained inputs and schema hints`

### §2 — Trigger input references

**Why:** If a trigger fires with data (e.g., a chat command captures the message text), there is no visible mechanism to reference that data in downstream nodes. Users must guess the variable names.

1. **Trigger data schema panel:**
   - When a trigger is selected, show a read-only "Available variables" panel listing the trigger's output keys and types.
   - Example for `chat_command`: `{ command: string, args: string, user_id: string }`
   - Example for `webhook`: `{ body: object, headers: Record<string, string> }`

2. **Variable picker in node fields:**
   - Next to any text input that supports variable interpolation (message body, condition expression), add a small "Insert variable" button.
   - Opens a dropdown of available variables: trigger outputs + named upstream node outputs.
   - Inserting adds `{data.variable_name}` at the cursor position.

3. **Highlighting:**
   - In message preview and expression fields, highlight `{...}` placeholders with a distinct color so users can see which parts are dynamic.

**Commit:** `feat(web-ui): trigger input reference panel and variable picker`

### §3 — Tooltips and inline help

**Why:** Nothing explains what any field does. A user would need to read source code to understand the workflow model.

1. Add a help tooltip to every field label in the properties panel:
   - "Platform": "Which adapter sends the message."
   - "Target User": "The user or room that receives the message."
   - "Tool Name": "The registered tool to invoke."
   - "Branches": "Possible outcomes. The LLM selects one based on the prompt."
   - "Expression": "A condition that evaluates to true or false."

2. Add an info icon (ⓘ) next to each node type in the canvas that shows a description on hover:
   - "Send Message: Delivers a message to a user or room."
   - "Tool Call: Invokes a registered tool with arguments."
   - "LLM Decision: Asks the LLM to choose between defined branches."

3. Add a "Getting Started" link in the editor header that opens a modal with:
   - "1. Choose a trigger. 2. Add nodes. 3. Connect them. 4. Save and activate."

**Commit:** `feat(web-ui): tooltips and inline help for every workflow editor field`

### §4 — Tests

1. **Trigger type dropdown test:** Mount editor. Assert dropdown renders human-readable labels. Selecting "Scheduled" shows cron builder.
2. **Cron builder test:** Select "Daily", pick 9 AM. Assert cron value is `"0 9 * * *"`. Assert preview shows "At 09:00 AM".
3. **Tool dropdown test:** Mount Tool Call node. Assert tool names render. Selecting a tool updates args placeholder.
4. **Variable picker test:** Mount Send Message node with a chat_command trigger. Click "Insert variable". Assert `{data.command}` inserted.
5. **Platform/User dropdown test:** Mount Send Message node. Assert PlatformDropdown and UserDropdown render with backend data.
6. **Tag chips test:** Mount LLM Decision node. Add "urgent" branch. Assert chip renders. Remove it. Assert gone.

**Commit:** `test(web-ui): workflow editor UX overhaul tests`

## Evaluation

- All trigger types display human-readable labels with descriptions
- Schedule trigger uses a builder with presets, validation, and natural-language preview
- tool_error trigger uses a tool dropdown with "Any" option
- All node property panels use constrained inputs (dropdowns, multi-selects, tag chips) instead of free-text
- Tool Call args have schema-aware forms or guided JSON textareas
- Users can see and insert trigger/upstream variables into message bodies and expressions
- Every field has a tooltip or helper text explaining its purpose

## Acceptance

- Frontend tests pass
- `npm run build` in `web-ui/` completes without errors
- Manual walkthrough: create a workflow with chat_command trigger → add Send Message node → select platform and user from dropdowns → insert trigger variable → save
- `mypy src/hestia` reports 0 new errors (if backend changes)
- `ruff check src/ tests/` clean on changed files
- `.kimi-done` includes `LOOP=L174`
