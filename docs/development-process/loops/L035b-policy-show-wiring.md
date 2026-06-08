# Kimi loop L35b — `_cmd_policy_show` derive from registry/config (drift fix)

## Hard step budget

≤ **3 commits**, ≤ **1 new test module**, scope strictly limited to the listed files. Stop after handoff commit; write `.kimi-done`; push; exit.

## Review carry-forward

From L35a (assume green merge ahead of this loop):

- Test baseline: **≥ 744 passed, 6 skipped** (L34 baseline + L35a tests).
- Mypy 0. Ruff 44.
- `style disable` is now a working `@click.pass_obj` command — pattern to copy if you find any other `*_disable` / `*_enable` bugs while in `cli.py`.

From `docs/development-process/reviews/v0.8.0-pre-release-plan.md` §2 and direct verification:

- `src/hestia/app.py` line 1186 defines `_cmd_policy_show`. The body (~170 lines) hard-codes:
  - `"Max attempts: 2"` (retry policy section, around line 1350) — should come from the active retry config / `PolicyConfig`.
  - The "tools requiring confirmation" list (`write_file`, `terminal`) — should come from iterating the tool registry and reading each tool's `requires_confirmation` flag.
  - The delegation keyword list (`delegate, subagent, spawn task, background task` and `research, investigate, analyze deeply, comprehensive`) — should come from the active `PolicyConfig.delegation_keywords` (added in L33c) and any sibling research-keyword constant in `src/hestia/policy/default.py`.
  - Trust profile name — currently the body lists individual `auto_approve_tools`, `scheduler_*`, `subagent_*` flags. It should also surface the active **preset name** (`cfg.trust.preset`).
  - Capability filtering rules — currently the per-`session_type` block builds blocked-tool reasons from a hand-maintained `if SHELL_EXEC ... elif WRITE_LOCAL ...` cascade. That's already deriving from `meta.capabilities` so it's fine; do **not** rewrite this block.

**Branch:** `feature/l35b-policy-show-wiring` from `develop` post-L35a.

**Target version:** **stays at 0.8.0**.

---

## Scope — `_cmd_policy_show` rewrite (in-place, same function)

This is a single-function refactor. Do **not** split helpers into a new module unless an extracted helper is reused outside `_cmd_policy_show`.

### §1 — Retry policy section

Replace:

```python
click.echo("  Max attempts: 2")
```

with the live value. Source priority (use the first that exists; verify by reading `src/hestia/policy/default.py` and `src/hestia/config.py`):

1. `app.policy.retry_max_attempts` (if exposed as a property/attribute)
2. `app.config.policy.retry_max_attempts` (if it lives on `PolicyConfig`)
3. A module-level constant (e.g. `DEFAULT_RETRY_MAX_ATTEMPTS`) imported from wherever `should_retry` lives

If none of those exist today, define `DEFAULT_RETRY_MAX_ATTEMPTS = 2` at module scope in the file that holds `should_retry`, expose it as `policy_engine.retry_max_attempts`, and read from there. **Do not** invent a `PolicyConfig.retry_max_attempts` field for L35b — that's a future loop. Just stop the hard-coding.

### §2 — Confirmation-required tool list

Replace:

```python
click.echo("    - write_file")
click.echo("    - terminal (for destructive operations)")
```

with:

```python
confirming = sorted(
    name
    for name in app.tool_registry.list_names()
    if app.tool_registry.describe(name).requires_confirmation
)
if confirming:
    for name in confirming:
        click.echo(f"    - {name}")
else:
    click.echo("    - (none)")
```

Verify the field name on `ToolMetadata` — it may be `requires_confirmation`, `confirmation_required`, or something similar. Use `git grep` in `src/hestia/tools/`. If the registry exposes a higher-level helper (e.g. `iter_with_confirmation()`) prefer it.

### §3 — Delegation keyword list

Replace:

```python
click.echo("    - Keywords: delegate, subagent, spawn task, background task")
click.echo("    - Research keywords: research, investigate, analyze deeply, comprehensive")
```

with:

```python
delegation_keywords = (
    app.config.policy.delegation_keywords
    if app.config.policy.delegation_keywords is not None
    else DEFAULT_DELEGATION_KEYWORDS
)
click.echo(f"    - Keywords: {', '.join(delegation_keywords)}")
```

(Import `DEFAULT_DELEGATION_KEYWORDS` from `src/hestia/policy/default.py`, where L33c put it.)

For the research-keyword line: if there's a sibling constant (`DEFAULT_RESEARCH_KEYWORDS` or similar), surface it the same way. If research keywords are still inlined inside `should_delegate` as a literal, leave the existing hard-coded line **but add a comment** flagging it for L38 to consolidate. Don't expand L35b's scope by hoisting the research list — that belongs in L38's "delegation keyword consolidation" commit.

### §4 — Trust preset name

In the existing TRUST PROFILE block (around line 1224), add **above** the per-flag listing:

```python
click.echo(f"  Active preset: {cfg.trust.preset or '(custom — no preset name)'}")
```

Verify the attribute name on `TrustConfig` (`preset`, `profile`, `name`, etc.). Don't rename it.

### §5 — Tests

`tests/unit/test_policy_show_wiring.py` (new) — uses `CliRunner` against the `policy show` command:

- `test_policy_show_reflects_registered_confirmation_tools` — register a fake tool with `requires_confirmation=True` via a custom `make_app` fixture; run `policy show`; assert the tool name appears under the confirmation section.
- `test_policy_show_reflects_zero_confirmation_tools` — registry with no `requires_confirmation` tools; assert `(none)` appears.
- `test_policy_show_reads_retry_max_attempts_from_engine` — patch `app.policy.retry_max_attempts = 5`; assert `Max attempts: 5` in output.
- `test_policy_show_reads_delegation_keywords_from_config` — `PolicyConfig(delegation_keywords=("only_this", "and_this"))`; assert `only_this, and_this` appears in keywords line.
- `test_policy_show_uses_default_keywords_when_config_none` — `PolicyConfig(delegation_keywords=None)`; assert one of the `DEFAULT_DELEGATION_KEYWORDS` entries (e.g. `delegate`) appears.
- `test_policy_show_surfaces_trust_preset` — `TrustConfig(preset="paranoid")`; assert `Active preset: paranoid` in output.

Use the existing `tests/conftest.py` fixtures for `CliAppContext` if available; otherwise build a minimal `CliAppContext` with stub stores.

---

## Commits (3 total)

1. `refactor(cli): derive policy show data from live registry and config`
2. `test(cli): lock policy-show wiring against drift`
3. `docs(handoff): L35b policy-show wiring`

Handoff doc is `docs/handoffs/L35b-policy-show-wiring-handoff.md`, ≤ 50 lines.

---

## Required commands

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/
```

Mypy 0. Ruff ≤ 44. Pytest must end at **≥ 750 passed** (744 + 6 new) or higher.

---

## `.kimi-done` contract

```
HESTIA_KIMI_DONE=1
LOOP=L35b
BRANCH=feature/l35b-policy-show-wiring
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

---

## Critical Rules Recap

- Do **not** bump `pyproject.toml`. Do **not** touch `CHANGELOG.md`.
- Do **not** rewrite the per-`session_type` blocked-tools cascade in `_cmd_policy_show` — it already derives from `meta.capabilities`. Out of scope.
- Do **not** consolidate the research-keyword list in this loop. Flag with a `# TODO(L38): ...` comment instead.
- Do **not** add `retry_max_attempts` as a new `PolicyConfig` field. Just stop the hard-coding by routing through whatever attribute already exists or by exposing a module-level constant.
- Push and stop after `.kimi-done`.
