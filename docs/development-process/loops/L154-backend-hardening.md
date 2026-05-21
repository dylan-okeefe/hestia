# L154 — Backend Hardening

**Status:** Spec only
**Branch:** `feature/l154-backend-hardening` (from `feature/workflow-builder`)
**Depends on:** L134

## Intent

Several backend issues reduce robustness and correctness: workflows have no way to set owner or trust level via the API (defeating trust enforcement), node capabilities aren't serialized, `list_workflows` has an N+1 query fetching active versions per row, `list_executions` has no upper bound on `limit`, `InvestigateNode` leaks all upstream data to tools, `WorkflowStore.create_tables` accesses private `_db._engine`, and there's ~80 lines of copy-pasted upsert logic that should be a helper.

## Scope

### §1 — Owner and trust level in workflow API

In `src/hestia/web/routes/workflows.py`:

1. In `create_workflow`: accept `owner_id` and `trust_level` in the request body. Default `owner_id` to the authenticated user's `platform_user` (from auth middleware state). Default `trust_level` to `"paranoid"`.
2. In `update_workflow` (PATCH): allow updating `owner_id` and `trust_level`. Validate that `trust_level` is one of the allowed values (`paranoid`, `prompt_on_mobile`, `household`, `developer`). Return 422 for invalid values.
3. Validate `trust_level` with an enum or a set check, not just free-text acceptance.

**Commit:** `feat(workflows): owner_id and trust_level settable via API`

### §2 — Node capabilities in API

In `src/hestia/web/routes/workflows.py`:

1. In `_version_to_api` (or equivalent serialization), include `capabilities` in each node's output dict.
2. In `create_version` (POST version endpoint), read `capabilities` from each node in the request payload and store it.
3. The `save_version` store method already serializes `n.capabilities` (confirmed in store.py line 133) — the issue is only at the API route layer not reading/writing it.

**Commit:** `feat(workflows): serialize node capabilities in version API`

### §3 — Fix N+1 query in list_workflows

In `src/hestia/web/routes/workflows.py`:

1. The list endpoint currently calls `get_active_version(workflow_id)` for each workflow in a loop. Replace with a single batch query.
2. In `src/hestia/workflows/store.py`, add `async def get_active_versions_batch(self, workflow_ids: list[str]) -> dict[str, WorkflowVersion | None]` that fetches all active versions in one query: `SELECT * FROM workflow_versions WHERE workflow_id IN (...) AND is_active = true`.
3. In the route, call `get_active_versions_batch([w.id for w in workflows])` once, then zip results.

**Commit:** `perf(workflows): batch active version fetch in list_workflows`

### §4 — Limit validation on list_executions

In `src/hestia/web/routes/workflows.py`:

1. Add `Query(ge=1, le=200)` constraint to the `limit` parameter: `limit: int = Query(default=50, ge=1, le=200)`.
2. This prevents `?limit=999999999` from loading the entire table.

**Commit:** `fix(workflows): cap list_executions limit at 200`

### §5 — InvestigateNode input scoping

In `src/hestia/workflows/nodes/investigate.py`:

1. Instead of passing the full `inputs` dict to every tool, only pass the keys specified in `node.config.get("input_keys", [])`. If `input_keys` is empty or not set, pass only the immediate predecessor's output (the first key in `inputs`).
2. This prevents leaking sensitive data from unrelated upstream nodes to tools that shouldn't see it.
3. Log a warning if `input_keys` references a key not present in `inputs`.

**Commit:** `fix(workflows): InvestigateNode scopes tool inputs to configured keys`

### §6 — Fix WorkflowStore.create_tables private access

In `src/hestia/workflows/store.py`:

1. Line 22: `if self._db._engine is None` — change to `if self._db.engine is None` (use the public property).
2. Verify the `Database` class exposes an `engine` property (it does — line 24 already uses `self._db.engine.begin()`). The `_engine` check on line 22 is inconsistent.

**Commit:** `fix(workflows): use public db.engine property in create_tables check`

### §7 — Extract upsert helper in WorkflowStore

In `src/hestia/workflows/store.py`:

1. `save_workflow` and `save_version` both contain nearly identical upsert logic (~40 lines each): dialect check → sqlite insert → on_conflict_do_update / pg insert → on_conflict_do_update / fallback select-then-insert.
2. Extract a private helper: `async def _upsert(self, table, values: dict, conflict_keys: list[str], update_keys: list[str]) -> None`.
3. The helper handles dialect detection, conflict resolution, and the fallback path.
4. Replace both copy-pasted blocks with calls to `self._upsert(...)`.

**Commit:** `refactor(workflows): extract _upsert helper in WorkflowStore`

### §8 — Test run accepts trigger payload

In `src/hestia/web/routes/workflows.py`:

1. The `test_run_workflow` endpoint accepts an optional `payload` parameter but the frontend never sends one. The executor should pass this payload as the trigger context, allowing users to simulate "what would happen if this webhook/command arrived."
2. Ensure the executor receives and uses `payload` as the initial input context for root nodes (nodes with no incoming edges). Currently it likely passes `{}`.

In `web-ui/src/api/client.ts`:

3. Update `testRunWorkflow` to accept an optional payload argument: `testRunWorkflow(id: string, payload?: Record<string, unknown>)`.
4. In the editor UI test-run flow, if the workflow trigger is `webhook` or `chat_command`, show a JSON textarea for the user to enter a sample payload before running.

**Commit:** `feat(workflows): test run accepts sample trigger payload`

### §9 — Tests

1. **Trust level validation test:** Try to create a workflow with `trust_level="admin"`. Assert 422 error.
2. **Owner default test:** Create a workflow without `owner_id`. Assert response has the authenticated user's platform_user as owner.
3. **Capabilities round-trip test:** Save a version with node capabilities. Fetch it. Assert capabilities are present.
4. **N+1 fix test:** Call list_workflows, assert only 2 DB queries made (one for workflows, one for active versions) — use query counting or mock.
5. **Limit cap test:** Call `?limit=9999`. Assert response contains at most 200 items (or that the query used 200).
6. **InvestigateNode scoping test:** Execute with `input_keys=["error_msg"]` and inputs containing `{"error_msg": "...", "secret_token": "..."}`. Assert tool only received `error_msg`.
7. **Upsert helper test:** Call save_workflow twice with same ID but different name. Assert second call updates, not duplicates.
8. **Test run with payload:** POST test-run with `{"command": "deploy", "args": "prod"}`. Assert executor receives payload as initial context.

**Commit:** `test(workflows): backend hardening tests`

## Evaluation

- Workflows can be created/updated with owner_id and trust_level via API
- Node capabilities survive API round-trip
- list_workflows makes 2 queries total, not N+1
- list_executions rejects limit > 200
- InvestigateNode only passes scoped inputs to tools
- WorkflowStore uses public `engine` property consistently
- Upsert logic is DRY (single helper, two call sites)
- Test run accepts and uses trigger payload

## Acceptance

- `pytest tests/unit/workflows/ -q` green
- `mypy src/hestia` reports 0 new errors
- `ruff check src/ tests/` clean on changed files
- `.kimi-done` includes `LOOP=L154`
