# L151 — Email Trigger + Internal Event Triggers

**Status:** Spec only
**Branch:** `feature/l151-email-internal-triggers` (from `feature/workflow-builder`)
**Depends on:** L134, L147

## Intent

The trigger system currently supports `manual`, `schedule`, `chat_command`, `message`, and `webhook`. Despite email being a configured platform adapter, there is no `email_received` trigger type. Additionally, there are no triggers for internal system events — "proposal approved", "tool error", "workflow completed" — which limits automation to external stimulus only. Internal event triggers would allow workflows to chain (workflow A completes → fires workflow B) and react to system state changes.

## Scope

### §1 — Email received trigger

In `src/hestia/workflows/triggers.py`:

1. Add `"email_received": "email"` to `TRIGGER_MAP`.
2. Add `_email_matches(self, workflow: Workflow, payload: Any) -> bool` that checks `trigger_config` fields: `from_address` (substring match on sender), `subject_contains` (substring match on subject). Both optional — if neither set, all emails match.

In `src/hestia/platforms/runners.py` (or whichever file handles inbound email processing):

3. When an inbound email is received, publish `app.event_bus.publish("email_received", {"from": sender, "subject": subject, "body": body_text, "platform": "email"})`.
4. If no email inbound processing exists yet, create a stub in `src/hestia/platforms/email_inbound.py` with a `process_inbound_email(app, sender, subject, body)` function that publishes the event. Document that this will be called by the email adapter once IMAP/webhook inbound is implemented.

In the frontend trigger config panel:

5. Add `"email"` to the trigger type dropdown options.
6. When selected, show optional fields: "From address (contains)" and "Subject (contains)".

**Commit:** `feat(workflows): email_received trigger type`

### §2 — Internal event triggers

In `src/hestia/workflows/triggers.py`:

1. Add entries to `TRIGGER_MAP`:
   - `"proposal_approved": "proposal_approved"`
   - `"proposal_rejected": "proposal_rejected"`
   - `"tool_error": "tool_error"`
   - `"workflow_completed": "workflow_completed"`
   - `"session_started": "session_started"`

2. Add matching methods:
   - `_proposal_matches`: match on `trigger_config.proposal_type` if set (optional filter)
   - `_tool_error_matches`: match on `trigger_config.tool_name` if set
   - `_workflow_completed_matches`: match on `trigger_config.source_workflow_id` if set (enables chaining)
   - `_session_started_matches`: always matches (no filtering needed)

In existing code, publish these events where appropriate:

3. In `src/hestia/reflection/` (proposal approval path): publish `"proposal_approved"` with `{"proposal_id": ..., "proposal_type": ..., "approved_by": ...}`.
4. In the workflow executor (after successful execution): publish `"workflow_completed"` with `{"workflow_id": ..., "execution_id": ..., "status": ...}`.
5. In the tool execution error path: publish `"tool_error"` with `{"tool_name": ..., "error": ..., "session_id": ...}`.
6. In session creation: publish `"session_started"` with `{"session_id": ..., "platform": ..., "platform_user": ...}`.

In the frontend trigger config panel:

7. Add all new trigger types to the dropdown.
8. For each, show relevant optional filter fields (e.g., "Source workflow" dropdown for `workflow_completed`, "Tool name" dropdown for `tool_error`).

**Commit:** `feat(workflows): internal event triggers (proposal, tool_error, workflow_completed, session)`

### §3 — Tests

1. **Email trigger matching test:** Create a workflow with `trigger_type="email"` and `trigger_config={"from_address": "alerts@"}`. Publish `email_received` with matching sender. Assert workflow matched.
2. **Email trigger no-match test:** Same workflow, publish with non-matching sender. Assert not matched.
3. **Workflow chaining test:** Create workflow B with `trigger_type="workflow_completed"` and `trigger_config={"source_workflow_id": "wf-A"}`. Publish `workflow_completed` with that ID. Assert B is matched.
4. **Tool error trigger test:** Create a workflow triggered on `tool_error` for `tool_name="http_get"`. Publish matching event. Assert matched.
5. **No filter test:** Create a `session_started` trigger workflow with empty config. Publish event. Assert always matches.

**Commit:** `test(workflows): email and internal event trigger tests`

## Evaluation

- Email received events can trigger workflows with optional from/subject filtering
- Internal system events (proposal approved, tool error, workflow completed, session started) can trigger workflows
- Workflow chaining works (A completes → B fires)
- All new trigger types appear in the frontend dropdown with appropriate config fields

## Acceptance

- `pytest tests/unit/workflows/ -q` green
- `mypy src/hestia` reports 0 new errors
- `ruff check src/ tests/` clean on changed files
- `.kimi-done` includes `LOOP=L151`
