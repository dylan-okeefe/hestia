# L179 — Rooms Migration & Interactive Workflow Nodes

**Status:** Spec only  
**Branch:** `feature/l179-rooms-interactive-nodes` (from `feature/user-registry-ui-rewrite`)  
**Depends on:** L172–L175

## Intent

The V2 review found that the Rooms section on Profile shows nothing despite an active Telegram group chat. Room auto-registration only fires on new group messages, and the migration utility only handles Matrix rooms from config. For Telegram groups, there's no migration path — the rooms table stays empty until someone sends a message after deployment.

Additionally, Dylan requested interactive workflow nodes: the ability for `send_message` nodes to collect user responses (approve/deny buttons or text input), making workflows truly interactive rather than one-way broadcasts.

## Scope

### §0 — Telegram group room migration

**Why:** Room auto-registration in `runners.py` only fires when a group chat message arrives after deployment. Pre-existing Telegram groups never get registered.

In `src/hestia/commands/users.py`:

1. During `migrate-users`, also scan for Telegram group chats:
   - If the Telegram adapter has been initialized and has chat history, iterate known group chats.
   - For each group chat, create a `Room` record with `platform='telegram'`, `platform_room_id=str(chat.id)`.
   - Link the admin user (or all known users) as room members.
   - If no chat history is available, add a log message: "No Telegram group chats found for migration. Rooms will be auto-registered on next group message."
2. Make the command idempotent for rooms (skip if room already exists).

Alternative if Telegram chat enumeration isn't available:

3. Add a new CLI command: `hestia migrate-rooms` that:
   - Prompts the admin for Telegram group chat IDs (or reads from a config list)
   - Creates Room records for each
   - Links specified users as members

**Recommendation:** Start with option 1 if the Telegram adapter exposes group chat IDs. Fall back to option 3 if not.

**Commit:** `feat(cli): migrate existing Telegram group chats to rooms table`

### §1 — Document room auto-registration

**Why:** Even with migration, admins need to understand when rooms appear.

In `docs/development-process/loops/L179-rooms-migration-and-interactive-nodes.md` (this spec):

1. Add a note to the handoff.

In the UI:

2. On Profile → Rooms section, when empty, show:
   - "No rooms yet. Telegram and Matrix group chats are registered automatically when a message is received. Run `hestia migrate-users` to register existing groups."

**Commit:** `docs(web-ui): explain room auto-registration in empty state`

### §2 — Interactive workflow nodes (approve/deny)

**Why:** Dylan requested `send_message` nodes support user responses — both approve/deny buttons and text entry responses. This makes workflows interactive.

**Backend changes in `src/hestia/workflows/`:**

1. Extend the `send_message` node config schema to include:
   ```json
   {
     "requires_response": true,
     "response_type": "buttons|text",
     "buttons": ["Approve", "Deny"],
     "timeout_seconds": 300
   }
   ```
2. In the executor, when a `send_message` node has `requires_response: true`:
   - Send the message with interactive elements (if platform supports it)
   - Wait for user response (blocking with timeout)
   - Store the response in the node's output context
   - If timeout, set output to `{ "response": null, "timed_out": true }`
3. For platforms that don't support interactive messages (e.g., Matrix, CLI), fall back to:
   - Sending the message + "Reply with: Approve or Deny"
   - Listening for the next message from the same user as the response

**Frontend changes in `web-ui/src/components/workflow-editor/NodePropertiesPanel.tsx`:**

4. In the Send Message node config panel, add:
   - Checkbox: "Wait for user response"
   - Radio: "Response type: Buttons / Free text"
   - If Buttons: tag-chip input for button labels (default: "Approve", "Deny")
   - Number input: "Timeout (seconds)" (default: 300)
5. Add helper text: "If enabled, the workflow pauses until the user responds or the timeout expires."

**Commit:** `feat(workflows): interactive send_message nodes with approve/deny and text responses`

### §3 — Natural-language cron in Config page

**Why:** Dylan requested that cron expressions in config values display as human-readable text.

In `web-ui/src/components/ConfigForm.tsx`:

1. Detect when a config value looks like a cron expression (5-field string with numbers, spaces, `*`, `-`, `,`, `/`).
2. If detected, render the value alongside `formatCron(value)` in a smaller, muted text below the input.
3. Example: input shows `0 9 * * 1`, below it shows "At 09:00 AM, only on Monday".

**Commit:** `feat(web-ui): human-readable cron preview in Config page`

### §4 — Tests

1. **Room migration test:** Mock Telegram adapter with 2 group chats. Run migration. Assert 2 Room records created.
2. **Interactive node config test:** Mount Send Message properties. Check "Wait for response". Assert button labels input appears.
3. **Interactive node execution test:** Execute workflow with send_message requiring response. Mock platform reply "Approve". Assert output contains `{ response: "Approve" }`.
4. **Cron preview test:** Config form with value `"0 9 * * 1"`. Assert preview text "At 09:00 AM" renders.

**Commit:** `test: rooms migration and interactive workflow nodes`

## Evaluation

- Telegram group chats can be migrated to the rooms table
- Profile empty state explains room auto-registration
- Send_message nodes support approve/deny buttons and text responses
- Workflow executor blocks on interactive nodes with timeout handling
- Cron expressions in Config show human-readable previews

## Acceptance

- `npm run build` in `web-ui/` passes
- Frontend tests pass
- `pytest tests/unit/ tests/integration/ -q` green on changed backend
- `mypy src/hestia` reports 0 new errors
- `ruff check src/ tests/` clean on changed files
- `.kimi-done` includes `LOOP=L179`
