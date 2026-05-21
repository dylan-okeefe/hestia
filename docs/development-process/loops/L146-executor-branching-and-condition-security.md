# L146 — Executor Branching + Condition Node Security

**Status:** Spec only
**Branch:** `feature/l146-executor-branching-security` (from `feature/workflow-builder`)
**Depends on:** L134, L137

## Intent

The DAG executor runs every node unconditionally regardless of branching decisions. Condition and LLM decision nodes compute their output but the executor never uses that output to gate downstream execution — every path fires. This is the single most critical bug in the workflow builder because it defeats the core value proposition of conditional logic. Additionally, the condition node's expression evaluator has a sandbox escape via unrestricted `getattr` and allows resource exhaustion via `operator.pow`.

## Scope

### §1 — Implement branch-aware execution in the executor

In `src/hestia/workflows/executor.py`:

1. After executing a node, check if it is a branching node (type `condition` or `llm_decision`).
2. For `condition` nodes: the output is a boolean. Mark edges with `source_handle="true"` as active if output is truthy, edges with `source_handle="false"` as active if falsy.
3. For `llm_decision` nodes: the output is a branch name string. Mark edges whose `source_handle` matches the branch name as active. All other edges from this node are inactive.
4. Maintain a set of "active edges" during execution. Before executing a node, check that at least one of its incoming edges is active (or the node is a root/entry node with no incoming edges). Skip nodes where all incoming edges are inactive.
5. Replace `list.pop(0)` in `_topological_sort` with `collections.deque.popleft()` for O(1) dequeue.
6. Use the injected `WorkflowStore` instead of instantiating a fresh `WorkflowStore(self._app.db)` internally (line 151). Accept `workflow_store` as an `__init__` parameter.

**Commit:** `fix(workflows): implement branch-aware DAG execution`

### §2 — Fix LLMDecisionNode return value

In `src/hestia/workflows/nodes/llm_decision.py`:

1. The last line returns `response` (full `ChatResponse`) instead of the extracted branch name. Change to return a new `ChatResponse(content=branch, prompt_tokens=response.prompt_tokens, completion_tokens=response.completion_tokens)` so the executor can still extract token counts while downstream nodes get the clean branch label.

**Commit:** `fix(workflows): LLMDecisionNode returns branch name not raw response`

### §3 — Secure the condition node expression evaluator

In `src/hestia/workflows/nodes/condition.py`:

1. In `_eval_node` for `ast.Attribute`: deny any attribute starting with `_`. Add: `if node.attr.startswith('_'): raise ValueError(f"Access to private attribute '{node.attr}' is not allowed")`.
2. Remove `ast.Pow: operator.pow` from `_BIN_OPS` entirely. Power operations are not needed for workflow conditions and create an unbounded resource exhaustion vector (`10 ** 10 ** 10`).
3. Before passing inputs to `_safe_eval`, normalize them to JSON-safe types: `inputs = json.loads(json.dumps(inputs, default=str))`. This ensures all values are plain dicts/lists/strings/numbers/booleans/None and prevents leaking rich Python objects to the evaluator.

**Commit:** `fix(workflows): secure condition node expression evaluator`

### §4 — Add multi-handle output to branching node components

In `web-ui/src/components/workflow-nodes/ConditionNode.tsx`:

1. Replace the single bottom `<Handle>` with two: `<Handle type="source" position="bottom" id="true" style={{left:'30%'}} />` and `<Handle type="source" position="bottom" id="false" style={{left:'70%'}} />`. Label them "True" and "False".

In `web-ui/src/components/workflow-nodes/LLMDecisionNode.tsx`:

1. Read `data.branches` (array of branch names). Render one `<Handle type="source" position="bottom" id={branchName} />` per branch, evenly spaced across the bottom.
2. Label each handle with the branch name.

Update `web-ui/src/pages/WorkflowEditor.tsx`:

1. When connecting from a branching node handle, set `sourceHandle` on the edge to the handle's `id` (React Flow does this automatically when handles have `id` props).

**Commit:** `feat(web-ui): multi-handle branching nodes for condition and LLM decision`

### §5 — Tests

1. **Executor branching test:** Build a diamond DAG: start → condition → (true branch: nodeA, false branch: nodeB) → end. Set condition to return `True`. Assert nodeA executed and nodeB was skipped. Repeat with `False`.
2. **LLM decision branching test:** Build a DAG with LLM decision node branching to three paths. Mock inference to return "branch_b". Assert only the branch_b downstream node executed.
3. **Condition security tests:**
   - Expression `x.__class__` raises `ValueError` about private attribute access
   - Expression `2 ** 100` raises `ValueError` (Pow removed)
   - Inputs are JSON-normalized (pass a dict with a datetime value, assert it becomes a string)
4. **LLMDecisionNode return value test:** Assert `node_results[0].output` equals the branch name string, not a ChatResponse object.
5. Update any existing tests that relied on all nodes executing unconditionally.

**Commit:** `test(workflows): branching execution and condition security tests`

## Evaluation

- All paths in a branching workflow correctly gate on the branch output
- Condition node rejects dunder attribute access and Pow expressions
- LLM decision node returns the selected branch name
- React Flow canvas shows distinct true/false handles on condition nodes and per-branch handles on LLM decision nodes
- Executor uses injected store, not a self-instantiated one
- `_topological_sort` uses deque

## Acceptance

- `pytest tests/unit/workflows/ -q` green
- `mypy src/hestia` reports 0 new errors
- `ruff check src/ tests/` clean on changed files
- `.kimi-done` includes `LOOP=L146`
