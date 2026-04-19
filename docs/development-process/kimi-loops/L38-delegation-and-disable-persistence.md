# Kimi loop L38 — delegation keyword consolidation + `*_disable` / `*_enable` persistence policy

## Hard step budget

≤ **5 commits**, ≤ **2 new test modules**, scope strictly limited to the listed files. Stop after handoff commit; write `.kimi-done`; push; exit.

## Review carry-forward

From L37 (assume green-merged ahead of this loop):

- Test baseline: **~775 passed, 6 skipped**.
- Mypy 0. Ruff ≤ 24 (post-crunch).
- `commands.py` is the canonical home for `_cmd_*`.
- `_cmd_policy_show` reads `app.config.policy.delegation_keywords` (L35b). The matching constant is `DEFAULT_DELEGATION_KEYWORDS` in `src/hestia/policy/default.py` (L33c). **A second hard-coded list still exists** somewhere in the policy module — likely in `should_delegate` itself or in a sibling research-keyword list.

From `docs/development-process/reviews/v0.8.0-pre-release-plan.md` Stage D L38 and Copilot finding #6.

**Branch:** `feature/l38-delegation-and-disable-persistence` from `develop` post-L37.

**Target version:** **0.8.1.dev2**.

---

## Scope

### §1 — Audit duplicate keyword lists

```bash
git grep -n -E '"(delegate|subagent|spawn task|background task|research|investigate|analyze deeply|comprehensive)"' src/hestia/
```

Catalog every literal keyword list in `src/hestia/policy/`. Expected findings:

- `DEFAULT_DELEGATION_KEYWORDS` in `default.py` (the public, configurable list — added L33c)
- A second list inside `should_delegate` (the inline literal Copilot #6 flagged)
- Possibly a `DEFAULT_RESEARCH_KEYWORDS` constant
- Possibly an inline research-keyword literal

Document the catalog in commit 1's message.

### §2 — Consolidate

Decide policy: **all keyword-driven delegation triggers route through `PolicyConfig`**.

- Promote any second inline list to a module-level constant (`DEFAULT_RESEARCH_KEYWORDS` if it doesn't exist).
- Add `research_keywords: tuple[str, ...] | None = None` to `PolicyConfig` if absent.
- `should_delegate` reads:

```python
delegation = self._config.delegation_keywords or DEFAULT_DELEGATION_KEYWORDS
research = self._config.research_keywords or DEFAULT_RESEARCH_KEYWORDS
```

- All inline literal keyword tuples in `should_delegate` are removed.
- `_cmd_policy_show` (in `commands.py` post-L36) gets a one-line update to surface the research keyword list the same way it surfaces delegation keywords (left as a `# TODO(L38)` in L35b).

Commit 1: `refactor(policy): route research keywords through PolicyConfig.research_keywords`

### §3 — `*_disable` / `*_enable` persistence audit

In `src/hestia/cli.py` and `src/hestia/commands.py`, find every command matching the patterns `style_(disable|enable)`, `reflection_(disable|enable)`, `web_search_(disable|enable)`, etc.

For each:

- Does the command mutate `app.config` in-memory only? Then it is **process-local**.
- Is the command's docstring honest about that? L35a fixed `style_disable`. Audit the rest.

Decision policy (per the pre-release plan): keep these commands **in-memory-only**. Atomic YAML write is non-trivial and risks losing user comments/formatting. The fix is **docstring + output message clarity**, not persistence.

Update each `*_disable` / `*_enable` command to:

- Use `@click.pass_obj` + the L35a docstring template (process-only + how to persist).
- Output: `{Feature} {action} for this process. To persist, set <yaml.path> = <value> in your config.`

Commit 2: `fix(cli): clarify in-memory-only semantics for *_disable / *_enable commands`

### §4 — Tests

`tests/unit/test_policy_research_keywords.py` (new):

- `test_default_research_keywords_used` — message containing `"investigate"` and tool-chain projection ⇒ `should_delegate(...)` True.
- `test_custom_research_keywords_override` — `PolicyConfig(research_keywords=("only_this",))` ⇒ `"investigate"` no longer triggers research-delegation.
- `test_empty_research_keywords_disables` — `PolicyConfig(research_keywords=())` ⇒ never triggers via research keywords.
- `test_delegation_and_research_independent` — `delegation_keywords=()` does not disable research keyword path, and vice versa.

`tests/cli/test_disable_enable_persistence_message.py` (new) — for each `*_disable` and `*_enable` command:

- `CliRunner().invoke(cli, ["<group>", "disable"])` ⇒ exit 0; output mentions "this process" and references the config path to persist.

Commit 3: `test(policy+cli): research-keyword config + disable/enable persistence messages`

### §5 — Bump + handoff

- `pyproject.toml` → `0.8.1.dev2`
- `uv lock`
- `docs/handoffs/L38-delegation-and-disable-persistence-handoff.md` (≤ 60 lines).

Commit 4: `chore(release): 0.8.1.dev2; L38 handoff`

---

## Required commands

```bash
uv run pytest tests/unit/ tests/integration/ tests/cli/ tests/docs/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

Mypy 0. Ruff ≤ 24. Pytest must end at **≥ 783 passed**.

---

## `.kimi-done` contract

```
HESTIA_KIMI_DONE=1
LOOP=L38
BRANCH=feature/l38-delegation-and-disable-persistence
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

---

## Critical Rules Recap

- **No YAML writes.** `*_disable` commands stay in-memory-only.
- **All keyword lists configurable.** Zero literal keyword tuples should remain inside `should_delegate` after this loop.
- **Audit, then consolidate.** Commit 1's message must include the keyword-list catalog.
- Push and stop after `.kimi-done`.
