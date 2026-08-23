# Review: `feature/audit-remediation-r1`

**Date:** 2026-08-23 · **Reviewer:** Claude (advisory) · **Base:** `develop` @ `6d36d45` · **Head:** `5f293e0`
**Scope reviewed:** 23 commits, 154 files, +8,037 / -1,550. Static review only; no test execution from this environment.

---

## Verdict

**Merge it, but not as one lump, and not before four fixes.**

The work is better than I expected from an overnight unattended run. The diagnoses are correct, the root causes are actually addressed rather than papered over, the commit messages are honest about tradeoffs, and the self-flagged "choices made" list is the single most valuable artifact in the branch: a model that tells you which of its own decisions were judgement calls is a model you can review efficiently.

That said, there are three real defects introduced, one security fix that is weaker than its commit message implies, and a process finding that matters more than any individual bug.

---

## The process finding: read this one first

Commit `a7339d4` says it plainly:

> `m010_execution_is_test` existed but was never appended to `MIGRATIONS`, so existing databases never received the `is_test` column and the live instance would have crashed on the new `save_execution` insert.

**The full gate suite passed with that defect in place.** 2,281 tests green, ruff clean, mypy clean, and a production-crashing migration bug sailed straight through. It was caught by the model re-reading its own work, not by the gates.

The audit's headline recommendation was "restore green gates so everything else becomes enforceable." This branch proves green gates are necessary but nowhere near sufficient. Concretely, before anything else lands:

- Add a test that asserts every `m###_*` function defined in `migrations/__init__.py` appears in `MIGRATIONS`, in order, with no gaps.
- Add a migration smoke test that opens a copy of a real pre-migration schema and runs the full chain.

That is maybe an hour of work and it closes an entire class of "green but broken" failures.

## Defects introduced

### 1. `investigate` tool gating can be bypassed with a non-list `tools` value (security, high)

`_gate_node_tools` in `executor.py` re-derives the tool list:

```python
raw = inputs.get("tools", node.config.get("tools"))
if isinstance(raw, str):
    names.extend(...)
elif isinstance(raw, list):
    names.extend(...)
```

`InvestigateNode` resolves the same value and then does `for tool_name in tools:` with no type check. So any shape that is neither `str` nor `list` produces **zero gate checks and full execution**. A dict is the obvious case: `{"tools": {"terminal": true}}` gates nothing and then iterates the dict's keys straight into `tool_registry.call("terminal", ...)`.

This is reachable exactly through the SEC-001 threat model: `tools` is resolved from node *inputs* with precedence over config, and node inputs come from upstream node outputs, which include webhook payloads and `http_request` node JSON bodies.

The underlying mistake is structural: the gate re-implements the node's resolution logic in a second place, with a comment saying "Mirror InvestigateNode._resolve precedence." That is the exact duplication class the audit itself flagged as debt, introduced by the remediation. Two fixes, in order of preference:

1. **Gate at the registry, not the call site.** Wrap `tool_registry` with a gated facade that the workflow executor injects, so the node cannot call an ungated tool even if the executor's pre-check misses it. This is the audit's own ARCH-001 recommendation and it makes the whole finding class go away.
2. **Minimum viable fix now:** extract one `resolve_tool_names(node, inputs)` helper used by both the gate and the node, and make it **deny on unrecognized shapes** rather than returning an empty list. Fail closed, consistent with everything else in this codebase.

Either way, add a test with `tools` supplied via node inputs (not config), and one with a dict-shaped value. The current SEC-001 tests only exercise the config path.

### 2. `unref()` is not in a `finally` in `engine.process_turn` (correctness, medium)

The lock fix is well reasoned and the waiter-aware pruning is the right call. But in `engine.py` the pairing is:

```python
        finally:
            current_turn_id.reset(turn_token)

    self._lock_manager.unref(session.id)
    self._lock_manager.release_unused(session.id)
```

`unref` sits outside the `try`. The broad `except Exception` catches most paths, but `CancelledError` is a `BaseException` and propagates: a cancelled turn (shutdown, client disconnect, task cancellation) leaks a permanent interest reference, and that session's lock is then never prunable for the process lifetime.

The leak direction is safe (locks are over-retained, not under-retained), so this is not a correctness hole in the mutual-exclusion sense. It is a slow unbounded-growth bug and it silently defeats the pruning this class exists to do. `compaction.py` got this right with `try/finally`; `engine.py` should match. One line.

Related, lower priority: `release_unused` reads `lock._waiters`, a CPython private. It works and the comment explains why, but it will break silently on an asyncio internals change. Worth a test that asserts the waiter-suppression behavior directly, so a future Python bump fails loudly instead of reintroducing BUG-001.

### 3. Streaming stall discards the partial answer from history (correctness, medium)

The behavior change itself is right: a truncated answer presented as complete was the worse failure. But `REMEDIATION_SUMMARY` claims "partial streamed text stays on screen plus a failure notice," and that is only half true. The text stays on screen because `stream_callback` already pushed it to the platform. Nothing persists it: `content_parts` is local and the `raise` skips assembly entirely.

Net result is a divergence between what the user sees and what the session actually contains. The next turn's context has a user message with no assistant reply, so the model will not know what it just said, and the user will reasonably assume it does. On a local llama.cpp setup where stalls are a real occurrence, this will produce confusing conversations.

Recommend persisting the partial as an assistant message flagged truncated (you already have the vocabulary for this from the degeneracy work), or, at minimum, saying explicitly in the failure notice that the partial text was discarded and will not be remembered.

The 180s prefill / 120s inactivity timeouts are generous enough that I am not worried about false-positive failures on your hardware.

### 4. `available_users` widened while SEC-004 was narrowing it (tradeoff, low but worth a decision)

The same branch that removed platforms and chat IDs from the unauthenticated roster as "an unauthenticated reconnaissance feed" then adds `platforms` back to that same endpoint for the login picker's buttons. Chat IDs are gone, which was the sharp part, so the net posture is still much better than before. But you are now telling an anonymous caller which users exist, their display names, and which messaging platforms each one uses, and the endpoint does a per-user identity query so it is also cheap DoS amplification.

This is a product call, not a bug. Options: keep it (it is a private-network dashboard), or return platforms only after a user is selected, or drop the picker entirely and have the user type an identifier. Flagging it because the branch made two decisions in opposite directions and only one of them is documented as deliberate.

## What is genuinely good

- **BUG-001 is correctly diagnosed.** The "asyncio.Lock reports unlocked between `release()` and waiter resumption" observation is subtle and right, and the refcount-plus-waiter-check fix addresses it rather than papering over it. The `_compact_locked` extraction to get a clean `try/finally` shows real care.
- **BUG-002's ownership re-checks** on `save`/`erase` are a better fix than the eviction lock change alone. Holding the pool lock across eviction I/O is the right trade given evictions are rare, and the comment says so explicitly instead of just doing it.
- **SEC-001 tests actually assert the right thing**: `registry.call.assert_not_called()` rather than just checking a status string. Whoever wrote these understood that a security test that passes when the tool ran but errored afterward is worthless.
- **The "deliberately NOT done" list** is correctly scoped. Every item on it genuinely does need your decision, and nothing that needed your decision got made anyway. That is the discipline that makes the rest trustworthy.
- **The `finish_reason == "unknown" -> "stop"` deletion** is the single highest-value line in the branch.

## Hygiene issues

**`web-ui/tsconfig.tsbuildinfo` is committed** in the final `docs: audit docs` commit and is not in `.gitignore`. It is a machine-local incremental build cache and will conflict on every branch forever. Delete it and gitignore it before merging.

**Commit 12 is mislabeled.** `chore: remove dead code` contains the SEC-002 `request_code` rewrite and the SEC-004 roster change: real auth behavior changes, in a commit whose message says it only deletes unused code. If you ever bisect an auth regression, that message will actively mislead you. It also carries the rebuilt `web/static/assets/*` bundle, which belongs with the frontend commit.

**Test coverage is thinner than the commit count suggests.** Net +37 new test functions against 59 finding IDs referenced in `src/`. Roughly a third of the fixes carry a dedicated regression test; the rest are asserted by comment only. That is not unreasonable for a batch this size, but do not read "2,281 passing" as "59 findings verified." The migration bug is the proof.

## Recommended merge plan

**Before merge (blocking, roughly half a day):**

1. Migration registration test plus migration chain smoke test.
2. `investigate` gating: shared resolver that fails closed on unknown shapes, plus the two missing tests. Do not merge the gating fix while it has a bypass.
3. `unref` into a `finally`.
4. Delete and gitignore `tsconfig.tsbuildinfo`.

**Before merge (cheap, do it anyway):**

5. Decide the streaming-partial question and either persist the partial or fix the failure notice wording.
6. Decide the `available_users` platforms question.

**Merge shape:** the branch is coherent enough to merge whole once those land, and the commits are individually clean enough that squashing would lose useful history. I would keep the commit sequence, amend the commit 12 message to name the auth changes, and merge to `develop`.

**Do not treat this as closing ARCH-001.** The audit found four ungated tool-invocation paths; this branch gates one of them, at a call site, for the destructive subset only. The gate still only restricts `SHELL_EXEC`, `WRITE_LOCAL`, and `EMAIL_SEND` on unattended channels, so `workflow.allow_listed_tools` remains decorative for everything else. The registry-level chokepoint is still the loop that needs writing.

**Suggested next loops:**

- **L245**: gate chokepoint at the registry, covering all four bypass paths, with `trust_level` becoming a real control.
- **L246**: migration and gate hardening, plus regression tests for the fixes in this branch that shipped without them.

## One note on the method

The overnight run worked because the audit that preceded it was specific: numbered findings, evidence, and an explicit "needs a human decision" boundary. The model did the bounded work and stopped at the boundary, which is exactly right. But the migration bug is a good reminder of the failure mode: an unattended agent optimizes for the signal it can see, and green gates were the signal. Anything the gates do not cover is where the misses will cluster. Worth keeping in mind for the next one: before the next unattended run, spend the hour making the gates cover the thing you are most afraid of.
