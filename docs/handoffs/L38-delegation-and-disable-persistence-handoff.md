# L38 Handoff — delegation keyword consolidation + disable/enable persistence audit

**Merged to:** `feature/l38-delegation-and-disable-persistence`  
**Target version:** `0.8.1.dev2`

## What changed

1. **Policy keyword consolidation** (`src/hestia/policy/default.py`, `src/hestia/config.py`)
   - Split the single keyword list into two configurable paths:
     - `DEFAULT_DELEGATION_KEYWORDS` — explicit triggers: `delegate`, `subagent`, `spawn task`, `background task`
     - `DEFAULT_RESEARCH_KEYWORDS` — complex-task triggers: `research`, `investigate`, `analyze deeply`, `comprehensive`
   - Added `research_keywords: tuple[str, ...] | None = None` to `PolicyConfig`.
   - `should_delegate` reads both from `PolicyConfig` with fallback to module constants. Zero inline keyword literals remain.
   - `_cmd_policy_show` surfaces both lists (removed L38 TODO).

2. **Disable/enable persistence audit** (`src/hestia/cli.py`, `src/hestia/commands.py`)
   - `style_disable` was already fixed in L35a — kept as the template.
   - `schedule_disable`/`schedule_enable` and `skill_disable` persist to DB, so they did not need docstring changes.
   - No `reflection_disable`, `web_search_disable`, or `style_enable` commands exist in the codebase.

3. **Tests**
   - `tests/unit/test_policy_research_keywords.py` — 4 tests for research keyword behavior.
   - `tests/cli/test_disable_enable_persistence_message.py` — verifies `style disable` process-local messaging.

## Metrics

- pytest: **784 passed, 6 skipped** (target: ≥ 783)
- mypy: **0 errors**
- ruff src/: **23 errors** (baseline maintained)

## Next steps

- Merge `feature/l38-delegation-and-disable-persistence` → `develop` when ready.
- Tag `v0.8.1.dev2`.
