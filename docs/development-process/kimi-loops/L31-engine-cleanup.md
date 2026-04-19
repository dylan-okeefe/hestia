# Kimi loop L31 — orchestrator engine cleanup

## Review carry-forward

(Cursor populates after L30 review.)

From **external code-quality review (2026-04-18)**, verified against `develop`:

- `src/hestia/orchestrator/engine.py::Orchestrator.process_turn` is **903 lines total file, ~500 in this method**, with the failure-bundle construction **duplicated almost verbatim** in the `ContextTooLargeError` handler and the generic `Exception` handler (~60 lines × 2). Same 8-line slot snapshot, same policy snapshot JSON assembly, same user_input_summary truncation, same `FailureBundle(...)` constructor.
- `_dispatch_tool_call` duplicates the confirmation check across the `call_tool` meta branch (~lines 834–860) and the direct-tool branch (~lines 875–900) — identical logic.
- `ToolCallResult(status="error", content=..., artifact_handle=None, truncated=False)` is constructed 8+ times in `_dispatch_tool_call`. Verbose; easy to forget defaults.
- Trace-recording block uses `locals().get("delegated", False)` defensively because the variable may not be in scope on early-exception paths. Smell — declare upfront.
- `process_turn` fetches `await self._store.get_messages(session.id)` **twice**: once at the top, once after `DONE` to mine artifact handles. Messages are not mutated between those points.
- Artifact handles are recovered by **regex** (`re.findall(r"artifact://...")`) over stored message strings, even though `ToolCallResult.artifact_handle` is the source of truth. Backward — accumulate from results during dispatch.

**Branch:** `feature/l31-engine-cleanup` from **`develop`** (post-L30 merge).

**Target version:** **0.7.5** (patch — pure refactor, no behavior change).

---

## Goal

Make `process_turn` and `_dispatch_tool_call` understandable by extracting the duplicated structures and removing the defensive `locals()` usage. **No new behavior. No new fields on public types.**

---

## Scope

### §-1 — Merge prep

Branch from `develop` post-L30. `git status` clean. Record baseline pytest/mypy.

### §0 — Cleanup carry-forward

From L30 (merged at `30a224f`, all manually rescued from a Kimi `max-ralph-iterations` exit — see L30 handoff for the full list, the items below are the ones L31 should still be aware of):

1. **Hard ruff baseline: 44.** `uv run ruff check src/` returns 44 errors at the L30 merge commit. **L31 must not regress this number.** The remaining lints are mostly `E501` (27), `SIM105` (5), `F841` (3), `SIM108` (3), `B027` (2), `E712` (2), `F401` (1), `SIM103` (1) — none in the orchestrator engine. If you touch the orchestrator and notice an easy `SIM105` (`try/except/pass` → `contextlib.suppress`) cleanup, take it as a freebie; do **not** make a project-wide ruff sweep part of L31.
2. **Test baseline: 691 passed, 6 skipped, 0 mypy errors.** Pure refactors must hit the same numbers (your new tests in §7 push the total up; that is fine).
3. **Kimi step budget.** L29 and L30 both hit `--max-ralph-iterations=100` and exited mid-flight. Your spec is **9 commits + 3 new test files**; that should fit comfortably under 100 steps if you do **not** chase ruff cleanups, do **not** rewrite unrelated code, and write `.kimi-done` immediately after the last commit lands. Push the branch and stop.
4. **`Orchestrator(...)` is now constructed in exactly one place** — `CliAppContext.make_orchestrator()` in `src/hestia/app.py`. If §6 (`ToolCallResult.error`) or any §1–§5 change requires updating call-site signatures, you only need to touch `make_orchestrator()` plus the orchestrator engine and its tests. Do not search-and-replace other files.
5. **`schedule run` daemon-tick gate** — the L30 fix gates reflection-scheduler ticks behind `app.config.reflection.enabled`. If your L31 work touches the orchestrator's interaction with the reflection runner, leave that gate alone.
6. **Pre-existing `aiosqlite` `RuntimeError: Event loop is closed` test-teardown warnings** are still present and unrelated to L31.

### §1 — Extract `_build_failure_bundle`

New private method on `Orchestrator`:

```python
def _build_failure_bundle(
    self,
    *,
    session: Session,
    turn: Turn,
    error: BaseException,
    state: TurnState,
    user_input: str,
    failure_kind: str,  # "context_too_large" | "exception"
) -> FailureBundle:
    """Construct a FailureBundle from common turn state.

    Centralises slot snapshot, policy snapshot JSON, and input summary
    truncation; previously duplicated across two except blocks."""
```

Delete the duplicated bodies in the two except branches; both call this helper. Slot snapshot still uses the existing `hasattr` guard (move it into the helper too — single source of truth).

### §2 — Hoist `delegated` and `tool_chain` declarations

At the top of the outer `try` in `process_turn`:

```python
delegated: bool = False
tool_chain: list[str] = []
```

Replace `locals().get("delegated", False)` in the trace-recording block with the bare local. Remove the now-redundant defensive idiom.

### §3 — Remove duplicate `get_messages` round-trip

Capture `history` once at the top. Reuse the same list for the post-DONE artifact accumulation step. Verify that the flow does not mutate `history` between the two original calls (Cursor confirmed it does not, but Kimi must re-verify and add a comment if there are now subtle ordering constraints).

### §4 — Accumulate artifact handles from `ToolCallResult`

Remove the `re.findall(r"artifact://...")` in `process_turn`. During tool dispatch, when a `ToolCallResult` carries `artifact_handle`, append it to a `turn_artifact_handles: list[str]` collected in the dispatch loop. Pass that list directly into the trace record / final response object that previously consumed the regex output.

`re.findall` import becomes unused; remove if so.

### §5 — Extract `_check_confirmation`

```python
async def _check_confirmation(
    self,
    *,
    tool: Tool,
    arguments: dict[str, Any],
    session: Session,
) -> ToolCallResult | None:
    """Return None if approved (or if the tool does not require confirmation),
    or a ToolCallResult(error=...) if denied / unable to confirm."""
```

Call from both branches of `_dispatch_tool_call`. The duplicated `if tool.requires_confirmation: ... if self._confirm_callback is None: ... await self._confirm_callback(...)` block goes away.

### §6 — `ToolCallResult.error` classmethod

In `src/hestia/tools/types.py`:

```python
@classmethod
def error(cls, content: str) -> "ToolCallResult":
    return cls(status="error", content=content, artifact_handle=None, truncated=False)
```

Replace every `ToolCallResult(status="error", content=..., artifact_handle=None, truncated=False)` in `engine.py` with `ToolCallResult.error(...)`. `git grep -n 'ToolCallResult(status="error"' src/hestia` should return only the classmethod itself.

### §7 — Tests

- `tests/unit/test_orchestrator_failure_bundle.py` — drive `process_turn` to (a) `ContextTooLargeError` path, (b) generic `Exception` path; assert that the resulting `FailureBundle` has the same shape from both, with the right `failure_kind`. This is the regression that proves the dedup did not change observable behavior.
- `tests/unit/test_orchestrator_confirmation_helper.py` — exercise `_check_confirmation` for: no-confirm tool ⇒ `None`; confirm denied ⇒ `ToolCallResult.error(...)`; confirm accepted ⇒ `None`.
- `tests/unit/test_orchestrator_artifact_accumulation.py` — run a fake tool that returns a `ToolCallResult` with `artifact_handle="artifact://abc"`; assert the trace record's artifact list is `["artifact://abc"]` and that the regex path is gone (`assert "re.findall" not in inspect.getsource(Orchestrator.process_turn)`).
- Existing engine tests must remain green unchanged.

### §8 — Version bump + handoff

- `pyproject.toml` → `0.7.5`.
- `uv lock`.
- `CHANGELOG.md`.
- `docs/handoffs/L31-engine-cleanup-handoff.md`.

**Commits:**

- `refactor(orchestrator): extract _build_failure_bundle helper`
- `refactor(orchestrator): hoist delegated/tool_chain locals; drop locals().get`
- `refactor(orchestrator): single history fetch in process_turn`
- `refactor(orchestrator): accumulate artifact handles from ToolCallResult`
- `refactor(orchestrator): extract _check_confirmation helper`
- `refactor(tools): add ToolCallResult.error classmethod`
- `test(orchestrator): regression coverage for failure bundle, confirmation, artifacts`
- `chore(release): bump to 0.7.5`
- `docs(handoff): L31 engine cleanup report`

---

## Required commands

```bash
uv lock
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/hestia tests
git grep -n 'ToolCallResult(status="error"' -- src/hestia | grep -v "def error"  # must be empty
git grep -n 'locals().get(' -- src/hestia                                       # must be empty
git grep -n 're.findall(r"artifact' -- src/hestia                               # must be empty
wc -l src/hestia/orchestrator/engine.py                                         # target ≤ 750
```

---

## `.kimi-done` contract

```
HESTIA_KIMI_DONE=1
LOOP=L31
BRANCH=feature/l31-engine-cleanup
COMMIT=<sha>
TESTS=passed=N failed=0 skipped=M
MYPY_FINAL_ERRORS=0
```

---

## Critical Rules Recap

- Pure refactor. No new fields on `Session`, `Turn`, `ToolCallResult`, `FailureBundle` other than the `error` classmethod.
- Behavior parity: existing engine tests pass unchanged.
- One commit per section.
- Push and stop.
