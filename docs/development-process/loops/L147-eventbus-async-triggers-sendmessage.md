# L147 — EventBus Async Fix + Trigger Registry Reload + SendMessageNode Field Mismatch

**Status:** Spec only
**Branch:** `feature/l147-eventbus-triggers-sendmessage` (from `feature/workflow-builder`)
**Depends on:** L134

## Intent

Three related runtime bugs prevent workflow triggers from ever firing through chat platforms:

1. `EventBus.publish()` is synchronous (returns `None`), but `runners.py` calls `await app.event_bus.publish(...)` in two places (lines 184, 194). This raises `TypeError: object NoneType can't be used in 'await' expression` every time a user sends a command or message on Telegram/Matrix. The webhook route correctly calls `publish()` without `await`, proving this works — but the chat paths are broken.

2. `TriggerRegistry.start()` loads all workflows once into `self._workflows` and never updates. Workflows created, deleted, or updated after startup are invisible to the trigger system — new workflows never fire, deleted ones remain active.

3. `SendMessageNode` expects config keys `user` and `text` (via `_resolve("user", ...)` and `_resolve("text", ...)`), but the frontend `WorkflowEditor` properties panel stores `target_user` and `message` in `node.data`. When the executor runs, both resolve to empty → `ValueError`.

## Scope

### §1 — Make EventBus.publish() async

In `src/hestia/events/bus.py`:

1. Change `def publish(self, event_type: str, payload: Any) -> None` to `async def publish(self, event_type: str, payload: Any) -> None`.
2. Keep the existing `asyncio.create_task` pattern for fan-out (handlers still run concurrently).
3. Store task references in a `set[asyncio.Task]` on the instance (`self._tasks`). Add a done callback to each task that removes it from the set. This prevents garbage collection of in-flight handlers (fixes BE-5 from the review).
4. Add `async def drain(self) -> None` that awaits all pending tasks — useful for graceful shutdown and testing.

Update `src/hestia/web/routes/workflows.py:265`:
- Change `event_bus.publish(...)` to `await event_bus.publish(...)` in the webhook endpoint.

`runners.py` already uses `await` — those calls become correct once `publish` is async.

**Commit:** `fix(events): make EventBus.publish async and retain task references`

### §2 — Add reload() to TriggerRegistry

In `src/hestia/workflows/triggers.py`:

1. Add `async def reload(self) -> None` that re-queries `self._workflow_store.list_workflows()` and replaces `self._workflows`. No need to re-subscribe handlers (they query `self._workflows` on each event).
2. Add `async def reload_one(self, workflow_id: str) -> None` that fetches a single workflow and updates or removes it from `self._workflows`. This is cheaper for single-workflow CRUD operations.

In `src/hestia/web/routes/workflows.py`:

3. After `save_workflow` (create/update) and `delete_workflow`, call `await ctx.trigger_registry.reload_one(workflow_id)`.
4. Add `trigger_registry: TriggerRegistry | None` to `WebContext`. If `None` (trigger registry not started), skip reload calls silently.

In `src/hestia/web/context.py`:

5. Add `trigger_registry` field (default `None`) to `WebContext`.

In `src/hestia/commands/serve.py`:

6. After creating the `TriggerRegistry`, store it in `WebContext`.

**Commit:** `fix(workflows): TriggerRegistry reload on workflow CRUD`

### §3 — Fix SendMessageNode field name mismatch

In `src/hestia/workflows/nodes/send_message.py`:

1. Change `_resolve("user", node, inputs)` to `_resolve("target_user", node, inputs)` with a fallback: `inputs.get("target_user", inputs.get("user", node.config.get("target_user", node.config.get("user"))))`. This accepts both naming conventions for backward compatibility.
2. Same pattern for `text`/`message`: try `message` first, fall back to `text`.
3. Update the error messages to reflect both field names: `"SendMessageNode requires 'target_user' (or 'user') in config or inputs"`.

**Commit:** `fix(workflows): SendMessageNode accepts target_user/message field names`

### §4 — Tests

1. **EventBus async test:** Publish an event, `await bus.drain()`, assert handler was called. Replaces the fragile `asyncio.sleep(0.01)` pattern in existing tests.
2. **EventBus task retention test:** Publish, immediately check `len(bus._tasks) > 0`. After drain, check it's 0.
3. **TriggerRegistry reload test:** Start registry, assert workflow list has N items. Add a workflow to the store, call `reload()`, assert list has N+1.
4. **TriggerRegistry reload_one test:** Call `reload_one(id)` with a workflow that was updated. Assert the new trigger_config is reflected in matching.
5. **SendMessageNode field resolution test:** Execute with `config={"target_user": "123", "message": "hello", "platform": "telegram"}`. Assert no error. Repeat with `{"user": "123", "text": "hello", "platform": "telegram"}` (legacy keys). Assert both work.
6. **Integration test:** Simulate a full path — call `publish("chat_command", ...)` → trigger registry matches workflow → executor runs → SendMessageNode executes with correct field mapping.

**Commit:** `test(workflows): event bus async, trigger reload, send message field mapping`

## Evaluation

- `await app.event_bus.publish(...)` no longer raises TypeError
- Creating a new workflow with a `chat_command` trigger and immediately issuing the command fires the workflow
- Deleting a workflow with a trigger stops it from firing
- SendMessageNode works with frontend field names (`target_user`, `message`)
- Event bus tasks are retained until completion (no GC risk)
- Existing fragile `sleep(0.01)` tests replaced with `drain()`

## Acceptance

- `pytest tests/unit/workflows/ tests/unit/events/ -q` green
- `mypy src/hestia` reports 0 new errors
- `ruff check src/ tests/` clean on changed files
- `.kimi-done` includes `LOOP=L147`
