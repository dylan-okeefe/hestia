# L40 — Copilot cleanup backlog (post-v0.8.0)

**Status:** Spec only. **Do not merge to `develop`** until a v0.8.1 (or
later) release-prep doc names this loop in scope. Per the post-release
merge discipline rule in `.cursorrules` (added 2026-04-19), this work
ships on feature branches and waits for explicit release inclusion.

**Source of findings:** Public Copilot review of v0.8.0 (April 18-19,
2026). All "non-blocker" items deferred from `v0.8.0-release-and-voice-launch.md`
Track 4. Six findings + three open `# TODO(L*)` markers.

**Suggested branch decomposition:** Cursor's call. The natural splits are:

- `feature/l40a-orchestrator-perf` — sequential tool dispatch
  (largest item; gets a dedicated branch).
- `feature/l40b-policy-cleanup` — `should_evict_slot`, `for_trust`
  identity comparison, `_count_tokens` cache key comment.
- `feature/l40c-email-and-docs` — EmailAdapter bare excepts,
  `prompt_on_mobile` docstring, open TODOs.

Or a single `feature/l40-copilot-cleanup` branch with one commit per
finding if Kimi's step budget can fit it (~6-8 commits + tests ≈ 250
steps, comfortable under the 250 mini-loop ceiling).

---

## Items

## Review carry-forward

- Gmail compatibility bug found during runtime smoke test (2026-04-19):
  `EmailAdapter.create_draft()` hardcodes the IMAP Drafts mailbox name as
  `"Drafts"` and `send_draft()` hardcodes `"Sent"`. Gmail uses
  `"[Gmail]/Drafts"` and `"[Gmail]/Sent Mail"`, so APPEND currently fails
  with `EmailAdapterError: Failed to append draft: NO` even when IMAP auth
  succeeds.
- Fold this into Item 5's EmailAdapter cleanup: introduce configurable IMAP
  special-folder names (or provider-aware autodetection via LIST + flags),
  update create_draft/send_draft/copy paths to use them, and add a regression
  test that covers a Gmail-like folder map.
- Also fix the teardown edge case exposed by the same failure path:
  `imap_session()` attempts `conn.close()` while in AUTH state and raises
  `IMAP4.error: command CLOSE illegal in state AUTH`. Close should be
  guarded (close only in SELECTED state, otherwise logout directly).

### 1. Sequential tool dispatch in orchestrator (correctness/perf)

**File:** `src/hestia/orchestrator/engine.py:676-690`

When the model returns multiple `tool_calls` in a single assistant
message and they have no inter-call dependency (e.g. `search_memory` +
`web_search` + `read_artifact`), the orchestrator dispatches them
sequentially via a `for` loop. Each tool's latency stacks. For a
three-tool turn with 500 ms each that's 1.5 s of avoidable latency.

**Fix sketch:**

```python
# Concurrent dispatch when no ordering metadata is set
results = await asyncio.gather(
    *[self._dispatch_tool_call(tc, session, turn) for tc in tool_calls],
    return_exceptions=True,
)
# Order is preserved by gather() → re-zip with the original tool_calls
# for confirmation flow + trace rendering downstream.
```

**Things to think hard about:**

- **Confirmation flow.** If two destructive tools both need
  confirmation, the user gets two confirmation prompts back-to-back. Is
  that UX acceptable? Alternative: serialize tools that require
  confirmation, gather() the rest. The current `_check_confirmation`
  helper makes the per-tool check, so the gate is at dispatch time.
- **Tool ordering metadata.** Check `tool.metadata` for an existing
  ordering flag. If none exists, this loop is also where one would be
  added. Most likely: no flag exists; default to "concurrent unless
  marked"; mark `email_*` tools as serial because IMAP session reuse
  and confirmation make sequential the safer default for the email
  family.
- **Trace rendering.** Trace store records tools in the order they
  were emitted by the model, not the order they completed. With
  `gather()`, completion order may differ. Preserve emission order in
  the trace.
- **Slot/inference contention.** If two tools both call out to
  llama.cpp (delegate_task can; web_search doesn't), they'll compete
  for the same slot. SlotManager handles this today via
  acquire/release, but verify gather() doesn't introduce a deadlock.

**Test:** New `tests/unit/test_orchestrator_concurrent_tools.py` with
two stub tools that each `await asyncio.sleep(0.5)` and return a string.
Assert the turn completes in < 0.7 s (sequential would be > 1.0 s).
Add a second test with one tool flagged ordering-required and assert
sequential dispatch.

**Risk:** Medium. Concurrent dispatch is genuinely more complex than
sequential; getting confirmation + trace ordering right is the bulk of
the work, not the gather() call itself.

### 2. `DefaultPolicyEngine.should_evict_slot` stub

**File:** `src/hestia/policy/default.py:132-137`

```python
def should_evict_slot(self, ...) -> bool:
    # Phase 2: actual policy
    return False
```

**Choose:**

- **(a) Remove the method.** Walk callers in
  `src/hestia/inference/slot_manager.py` and the orchestrator. If no
  one calls it through the policy interface (only direct `False`-
  returning code paths), delete the method and the matching `Protocol`
  abstract entry.
- **(b) Mark explicitly.** Replace body with
  `raise NotImplementedError("Slot eviction policy not implemented; SlotManager evicts on demand")`.
  Then update callers to handle the exception or remove the call.

Cursor decides based on caller audit. **Audit first**, then pick. Do
not silently leave the stub.

**Test:** If (a), delete the matching test in
`tests/unit/test_policy_engine.py`. If (b), add a regression test that
calling the method raises.

### 3. `HestiaConfig.for_trust` identity comparison

**File:** `src/hestia/config.py:426`

The `for_trust` factory uses `if for_trust is TrustLevel.HIGH` to
dispatch. This works today because `TrustLevel` is a module-level
singleton enum. It will silently miss after a JSON round-trip
(deserialization creates a new instance) — and the spec already
mentions JSON-loaded configs as a near-term goal.

**Fix:** Replace `is` with `==`. Add a regression test that
deserializes a `TrustLevel` from JSON and confirms `for_trust` still
dispatches correctly.

```python
# tests/unit/test_for_trust_value_equality.py
def test_for_trust_dispatches_after_json_roundtrip():
    cfg = HestiaConfig.for_trust(TrustLevel.HIGH)
    serialized = cfg.trust.value  # likely "high"
    revived = TrustLevel(serialized)
    assert revived is not TrustLevel.HIGH  # different identity
    assert revived == TrustLevel.HIGH      # same value
    cfg2 = HestiaConfig.for_trust(revived)
    assert cfg2.trust == cfg.trust
```

### 4. `ContextBuilder._count_tokens` cache key comment

**File:** `src/hestia/context/builder.py:449`

The cache key is `(role, content)`. `reasoning_content` and
`tool_call_id` are not included. This is intentional but undocumented.
Add a docstring/comment explaining:

- `reasoning_content` is stripped before sending to llama.cpp, so it
  doesn't contribute to the actual prompt token count.
- `tool_call_id` is rendered into the `tool` role's prefix, but the
  prefix length is constant per role, so it's safe to bucket all
  tool-result messages with the same content under one cache entry.
  *(Verify this claim by reading the rendering code; if the prefix
  varies, the comment instead documents that variant.)*

**No code change.** Just a comment. ~5 lines.

### 5. EmailAdapter bare `except:` clauses

**File:** `src/hestia/email/adapter.py:139, 147, 158`

Three bare `except:` blocks swallow exceptions silently in IMAP
recovery paths.

**Fix:** Narrow to `(IMAPException, ConnectionError, OSError)` (or
whatever the matching exception types are — verify by reading the
docstrings of `imaplib.IMAP4` operations involved). Log at `DEBUG`
before swallowing.

```python
try:
    conn.close()
except (imaplib.IMAP4.abort, imaplib.IMAP4.error, OSError) as e:
    logger.debug("IMAP close suppressed: %s", e)
```

Three sites → three identical-shape changes. ~9 lines total.

### 6. `prompt_on_mobile` docstring drift

**File:** `src/hestia/config.py:414-431` (the `for_trust` docstring)

The current docstring claims `prompt_on_mobile` blocks until
confirmation. The implementation routes through the platform's confirm
callback, which is fire-and-forget (the platform decides whether to
block). Rewrite the docstring to match the implementation:

> `prompt_on_mobile`: when set, destructive tool dispatch routes
> through the platform's confirm callback before executing. Whether
> the call blocks the conversation thread depends on the platform
> (Telegram inline keyboards block; Matrix reply-pattern doesn't).

While here, document that `prompt_on_mobile` preset has both
`handoff` and `compression` enabled — currently implied by the
factory function but not stated.

### 7. Open `# TODO(L*)` markers

**Choose for each:** implement, OR convert to a tracked GitHub issue
(open the issue manually after L40 lands; spec just notes it's
GH-tracked). No bare TODO survives.

- **`src/hestia/orchestrator/engine.py:???`** — `# TODO(L31): consider
  surfacing turn-level slot snapshots in failure bundles`. Was deferred
  in L31. Currently `slot_snapshot` already lives on `FailureBundle`;
  the TODO is stale. **Action:** delete the TODO comment.
- **`src/hestia/inference/slot_manager.py:???`** — `# TODO(L?): real
  eviction policy`. Subsumed by item 2 above (`should_evict_slot`
  stub). **Action:** resolve via item 2's audit; delete TODO.
- **`src/hestia/style/builder.py:???`** — `# TODO: ...`. Last loop
  (L35a/b) hardened the style module surface but left a TODO. Read it,
  decide, act.

`grep -rn '# TODO(L' src/hestia/` to find them all; the spec list above
may be incomplete by 1-2 markers since the codebase moves between
when the spec is written and when Kimi runs.

---

## Acceptance

- All seven items addressed (or cleanly converted to a tracked issue
  with a comment pointing at the issue URL).
- Test count goes up by 2-3 (the gather test, the for_trust JSON test,
  optionally the should_evict_slot regression).
- `mypy src/hestia` → 0 errors (was 0 at v0.8.0).
- `ruff check src/` → ≤ 23 errors (no new ruff debt; reductions
  welcome).
- `tests/unit/ tests/integration/ tests/cli/ tests/docs/` → all pass.
- No new items in CHANGELOG "Known issues" — every item from v0.8.0's
  Known issues section either ships in v0.8.1 or is moved to a tracked
  GitHub issue with a link from CHANGELOG.

## Branch / merge discipline

- Each branch named per Cursor's chosen decomposition.
- Branch is pushed to `origin` after the loop completes.
- **Branch does NOT merge to `develop`** at completion. Per
  `.cursorrules`, merging waits for the v0.8.1 release-prep doc to
  name the branch in scope.
- Handoff written to `docs/handoffs/L40[a-c]-handoff.md` regardless of
  merge state.

## Critical Rules Recap

- §-1: do NOT merge previous phase into develop. Branch from `develop`,
  push to origin/<branch>, stop. Release-prep doc will merge later.
- §0: no carry-forward — this is the first loop after v0.8.0.
- One commit per item (or per natural grouping; Cursor's call). One
  test file per code-changing item where coverage is non-trivial.
- Final `.kimi-done` includes `LOOP=L40a` (or whichever Cursor
  spawned), `BRANCH=feature/l40*`, `COMMIT=<sha>`, `TESTS=<count>
  passed`, `MYPY_FINAL_ERRORS=0`, `RUFF_SRC=<count>`.
- Handoff at `docs/handoffs/L40[a-c]-*-handoff.md`.
