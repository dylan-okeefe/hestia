# Kimi loop L33c — skills experimental feature flag + minor polish

## Hard step budget

≤ **5 commits**, ≤ **2 new test modules**, scope strictly limited to the listed files. Stop after handoff commit; write `.kimi-done`; push; exit.

## Review carry-forward

From L33b (merged at `<TBD>`):

- Test baseline: **<TBD>**.
- Mypy 0. Ruff ≤ 44.

From the external code-quality review:

- The skills framework (`@skill` decorator, `SkillState`, `SkillStore`, CLI commands `hestia skills *`, DB table) is **not invoked anywhere** during a turn. README acknowledges it as preview, but the public-facing decorator + CLI look ready-to-use. A user who writes a skill will be confused when nothing happens.
- `_format_datetime` is defined as a closure inside the schedule-show command capturing nothing. Belongs at module scope so other commands can use it.
- `DefaultPolicyEngine.should_delegate` matches keywords (`"research"`, `"analyze deeply"`) inline. Surprising trigger paths (e.g. `"I'd like to research my family history"` ⇒ delegation). Move to a named module-level constant; expose via `PolicyConfig.delegation_keywords` so it's tunable.
- `MatrixAdapter._extract_in_reply_to` schema validation is fine in code; needs a regression test to lock the contract before any future "simplification".

**Branch:** `feature/l33c-skills-flag-and-polish` from `develop` post-L33b.

**Target version:** **0.7.11** (patch).

---

## Scope

### §1 — Skills experimental feature flag

In `src/hestia/skills/__init__.py` (or wherever the public surface lives — verify with `git grep`):

- Add `def _experimental_enabled() -> bool: return os.environ.get("HESTIA_EXPERIMENTAL_SKILLS") == "1"`.
- Define `class ExperimentalFeatureError(HestiaError): ...` if not already present.
- The `@skill` decorator and `SkillRegistry.register` (and any `SkillStore.save` public entry) **raise `ExperimentalFeatureError`** when called without the env var set. Error message:
  > "Skills are an experimental preview. Set `HESTIA_EXPERIMENTAL_SKILLS=1` to opt in. See README.md#skills."
- `hestia skills *` CLI commands check the flag at command entry; print an informative message and exit nonzero (`sys.exit(1)`) if disabled.
- README's skills section (already exists) → rename heading to "Skills (experimental preview)" and add a one-paragraph callout explaining the env var and that skills are not invoked in a normal turn yet.

### §2 — `_format_datetime` to module scope

Find the closure:

```bash
git grep -n "_format_datetime" -- src/hestia
```

Move it to module scope in the same file (do **not** create a new util module — the file it's in is the only consumer right now). Update callers within the file. No behavior change.

### §3 — `should_delegate` keyword constant + config

In `src/hestia/policy/default.py` (or wherever `DefaultPolicyEngine.should_delegate` lives):

- Define `DEFAULT_DELEGATION_KEYWORDS: tuple[str, ...] = (...)` at module scope, populated from the current inline list.
- In `src/hestia/config.py` (`PolicyConfig` dataclass), add `delegation_keywords: tuple[str, ...] | None = None`.
- `should_delegate` reads from `self._config.delegation_keywords or DEFAULT_DELEGATION_KEYWORDS`.
- Docstring on `should_delegate` calls out the surprising triggers ("I'd like to research my family history" ⇒ delegation) and recommends overriding via config for production.

### §4 — Tests

`tests/unit/test_skills_feature_flag.py`:

- `test_skill_decorator_without_flag_raises` (use `monkeypatch.delenv("HESTIA_EXPERIMENTAL_SKILLS", raising=False)`).
- `test_skill_decorator_with_flag_works` (`monkeypatch.setenv("HESTIA_EXPERIMENTAL_SKILLS", "1")`).
- `test_cli_skills_list_disabled_message` — invoke `hestia skills list` without the flag; assert nonzero exit and stderr contains "experimental preview".
- `test_cli_skills_list_with_flag_works` — sets flag, lists empty registry, exit 0.

`tests/unit/test_policy_delegation_keywords.py`:

- `test_default_keywords_used` — message containing `"research"` ⇒ `should_delegate(...)` True.
- `test_custom_keywords_override` — config `delegation_keywords=("only_this",)` ⇒ `"research"` no longer delegates.
- `test_empty_tuple_disables_keyword_delegation` — `delegation_keywords=()` ⇒ never delegates by keyword.

`tests/unit/test_matrix_in_reply_to_parser.py`:

- `test_well_formed_reply` — fully nested `m.relates_to.m.in_reply_to.event_id` ⇒ returns the id.
- `test_missing_relates_to` ⇒ None.
- `test_relates_to_not_dict` (string) ⇒ None (no exception).
- `test_in_reply_to_not_dict` ⇒ None.
- `test_event_id_not_string` ⇒ None.
- `test_event_source_raises_on_access` (use a Mock that raises) ⇒ None (defensive swallow).

### §5 — Version bump + CHANGELOG + ADR + handoff

- `pyproject.toml` → `0.7.11`.
- `uv lock`.
- CHANGELOG entry under `[0.7.11] — 2026-04-18`.
- `docs/adr/ADR-0022-skills-preview-feature-flag.md` — short ADR documenting the gate, the env var name, and the rejection of "silent no-op" as too confusing for a public release.
- `docs/handoffs/L33-perf-and-polish-arc-handoff.md` — single handoff covering L33a + L33b + L33c. Include final test counts, ruff baseline, and a list of the user-visible behavior changes shipped by the arc.

---

## Commits (5 total)

1. `feat(skills): gate experimental framework behind HESTIA_EXPERIMENTAL_SKILLS flag`
2. `refactor(cli): hoist _format_datetime to module scope`
3. `feat(policy): expose delegation_keywords on PolicyConfig`
4. `test(matrix+policy+skills): lock parser contract, delegation keywords, and skills flag`
5. `chore(release): bump to 0.7.11; ADR-0022; L33-arc handoff`

(The last commit bundles three doc/version files because they are tiny and naturally cohere.)

---

## Required commands

```bash
uv lock
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/
```

Mypy 0. Ruff ≤ 44.

---

## `.kimi-done` contract

```
HESTIA_KIMI_DONE=1
LOOP=L33c
BRANCH=feature/l33c-skills-flag-and-polish
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

---

## Critical Rules Recap

- Skills flag MUST raise (not silently no-op). Visibility > convenience.
- README touch is one section heading + one paragraph; do **not** rewrite the README in this loop.
- Push and stop.
