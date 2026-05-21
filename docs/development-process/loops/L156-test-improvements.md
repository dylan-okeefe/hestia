# L156 — Test Improvements

**Status:** Spec only
**Branch:** `feature/l156-test-improvements` (from `feature/workflow-builder`)
**Depends on:** L146, L147, L148

## Intent

The workflow builder test suite has structural weaknesses that reduce confidence: event bus tests rely on fragile `asyncio.sleep(0.01)` timing, the executor test for failure propagation uses unconnected nodes (execution order is undefined), there are no edge-case tests for branching (nested conditions, multiple branches converging), and the frontend has no test coverage for error states. This loop hardens the test suite.

## Scope

### §1 — Replace fragile timing in event bus tests

In `tests/unit/events/test_bus.py` (or equivalent):

1. Replace all `await asyncio.sleep(0.01)` waits with `await bus.drain()` (from L147 §1).
2. This makes tests deterministic — they complete when all handlers finish, not after an arbitrary sleep that may be too short on slow CI or too long for fast feedback.
3. If any test intentionally tests timeout behavior, use `asyncio.wait_for` with an explicit timeout instead of sleep.

**Commit:** `test(events): replace sleep-based timing with deterministic drain()`

### §2 — Fix executor test with unconnected nodes

In `tests/unit/workflows/test_executor.py`:

1. Find `test_node_failure_stops_execution` (or similar test with unconnected nodes).
2. Add edges between nodes to create a defined execution order: `nodeA → nodeB → nodeC`. Set nodeB to raise an exception.
3. Assert: nodeA executed (before failure), nodeB failed, nodeC was NOT executed (failure stops downstream).
4. The current test only works by accident — if topological sort implementation changes, the test may pass/fail randomly.

**Commit:** `test(workflows): fix executor failure test to use connected DAG`

### §3 — Branching edge-case tests

In `tests/unit/workflows/test_executor.py`:

1. **Nested branching:** condition → (true: another condition → (true: nodeA, false: nodeB), false: nodeC). Set outer=True, inner=False. Assert: nodeB executed, nodeA and nodeC skipped.
2. **Converging branches:** condition → (true: nodeA, false: nodeB) → merge node. Both branches lead to the same merge node. Set condition=True. Assert: nodeA executed, nodeB skipped, merge node executed (because at least one incoming edge is active).
3. **Dead branch propagation:** condition(false) → nodeA → nodeB → nodeC. Assert all three are skipped (inactivity propagates through the chain, not just one hop).
4. **LLM decision with unknown branch:** LLM returns "branch_x" but only "branch_a" and "branch_b" edges exist. Assert: no downstream nodes execute, execution completes without error (graceful handling of unexpected branch names).
5. **Multiple roots:** DAG with two entry points (no incoming edges). Assert both execute regardless of branching state of other subgraphs.

**Commit:** `test(workflows): branching edge case tests (nested, converge, dead propagation)`

### §4 — Webhook authentication edge cases

In `tests/unit/workflows/test_webhooks.py`:

1. **Replay attack:** Same valid signature sent twice. Assert both succeed (no nonce requirement for v1, but document that this is a known limitation).
2. **Empty body:** Send webhook with empty body and valid HMAC of empty string. Assert 202.
3. **Non-JSON body:** Send plain text body with valid HMAC. Assert 202 and body decoded as string.
4. **Multiple workflows same endpoint:** Two workflows with same endpoint but different secrets. Assert the correct workflow fires based on which secret validates (or document that only one secret per endpoint is supported and the second workflow creation should fail).

**Commit:** `test(workflows): webhook authentication edge cases`

### §5 — Frontend error state tests

In `web-ui/src/` test files:

1. **Network failure on save:** Mock `saveWorkflowVersion` to reject. Assert error message displays in toolbar.
2. **Network failure on load:** Mock `fetchWorkflow` to reject. Assert error state renders (not blank canvas).
3. **Invalid workflow ID:** Navigate to `/workflows/nonexistent-id`. Assert 404-style message.
4. **Test run failure:** Mock `testRunWorkflow` to reject. Assert error shows in test result panel.
5. **`err: any` type fix in Scheduler.tsx:** The copilot flagged `err: any` in a catch block. Change to `err: unknown` and use `err instanceof Error ? err.message : String(err)` pattern for type safety.

**Commit:** `test(web-ui): error state coverage and type safety fixes`

### §6 — Node placement determinism

In `web-ui/src/pages/WorkflowEditor.tsx`:

1. Replace `Math.random() * 200 + 50` for new node position with a deterministic placement: offset from the last added node (e.g., `lastNode.position.y + 100`) or center of the current viewport.
2. This isn't purely a test concern — random placement makes automated screenshot-based testing unreliable and is confusing UX. Place new nodes below the lowest existing node with a fixed vertical offset.

**Commit:** `fix(web-ui): deterministic node placement below last node`

### §7 — Tests for §6

1. Add three nodes sequentially. Assert each is placed below the previous (y increases monotonically).
2. Add a node to an empty canvas. Assert it's placed at a sensible default position (e.g., center of viewport or fixed origin like `{x: 250, y: 100}`).

**Commit:** `test(web-ui): deterministic node placement tests`

## Evaluation

- Zero `asyncio.sleep` calls in event bus tests
- Executor failure test uses properly connected DAG with defined order
- Branching tests cover nested, converging, dead propagation, and unknown branch scenarios
- Webhook tests cover empty body, plain text, and multi-workflow edge cases
- Frontend tests verify error states render correctly
- Node placement is predictable and testable

## Acceptance

- `pytest tests/unit/ -q` green
- Frontend tests pass
- `mypy src/hestia` reports 0 new errors
- `ruff check src/ tests/` clean on changed files
- `.kimi-done` includes `LOOP=L156`
