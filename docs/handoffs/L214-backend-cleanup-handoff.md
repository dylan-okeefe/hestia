# L214 — Backend Cleanup & Correctness Handoff

## Completed Work

### §1 — M1: Auto-approve deny-list inconsistency
- **Files:** `src/hestia/policy/engine.py`, `src/hestia/policy/default.py`, `src/hestia/orchestrator/execution.py`
- `auto_approve` now accepts an optional `registry` parameter.
- Scheduler-tick fail-closed check keys on capabilities (`SHELL_EXEC`, `WRITE_LOCAL`, `EDIT_FILE`, `EMAIL_SEND`) via the registry, matching `filter_tools`.
- Hardcoded tool names remain as a fallback when registry is unavailable.
- Confirmed registered email tool name is `email_send` (not `send_email`).

### §2 — M2: SSRF misses IPv4-mapped IPv6
- **File:** `src/hestia/tools/builtin/http_get.py`
- Added `100.64.0.0/10` (CGNAT) to blocked ranges.
- `_assert_ip_allowed` now normalizes IPv4-mapped IPv6 via `ip.ipv4_mapped` before range checks.
- Added `not ip.is_global` as a broader guard before the explicit range list.
- Added tests for IPv4-mapped IPv6 loopback and metadata endpoints.

### §3 — M3: Calibration file CWD-relative path
- **File:** `src/hestia/context/builder.py`
- Default calibration path now resolves from the package root (`Path(__file__).parent.parent.parent / "docs" / "calibration.json"`) instead of process CWD.
- Logs a warning when calibration file is missing.
- Guards `body_factor == 0` in both `from_calibration_file` and `_apply_correction`.

### §4 — M4: Dead code under web/routes/
- Deleted unused files:
  - `src/hestia/web/routes/execution_store.py`
  - `src/hestia/web/routes/interpolation.py`
  - `src/hestia/web/routes/models.py`
  - `src/hestia/web/routes/response_store.py`
  - `src/hestia/web/routes/triggers.py` (canonical is `workflows/triggers.py`)
  - `src/hestia/web/routes/nodes/` directory (stale copies of workflow nodes)

### §5 — M5: Duplicate web-search tools
- **Files:** `src/hestia/app.py`, `src/hestia/orchestrator/execution.py`, `src/hestia/orchestrator/quality.py`, `src/hestia/tools/builtin/http_get.py`
- `web_search` (configurable factory) is now the canonical registered tool.
- Removed `search_web` fallback registration from `app.py`.
- Removed `search_web` references from emoji map, read-only tool list, and tool descriptions.

### §6 — M6: Unbounded reasoning text on done path
- **File:** `src/hestia/orchestrator/execution.py`
- Done path now truncates `reasoning_content` to 2000 chars (with "... (reasoning truncated)" suffix), matching the tool-call path.

### §7 — Low: Injection scanner efficiency
- **File:** `src/hestia/orchestrator/execution.py`
- Removed duplicate `_scan_tool_result` call from `_dispatch_tool_call`.
- Tool results are now scanned exactly once in the reassembly loop.

## Quality Gates

| Gate | Status | Notes |
|------|--------|-------|
| `pytest tests/unit/ tests/integration/` | ✅ 1695 passed, 6 skipped | |
| `mypy src/hestia` | ✅ No issues | |
| `ruff check src/ tests/` | ⚠️ 138 pre-existing errors | None in modified files; base branch had 148 |

## Commits

1. `fix(policy): key auto_approve fail-closed on capabilities via registry`
2. `fix(security): normalize IPv4-mapped IPv6, add CGNAT, use is_global guard in SSRF`
3. `refactor(context): resolve calibration path from package, warn on missing, guard body_factor==0`
4. `chore: delete dead code under web/routes (execution_store, interpolation, models, response_store, triggers, nodes)`
5. `refactor: make web_search canonical, remove search_web registration and references`
6. `fix(orchestrator): cap reasoning text to 2000 chars on done path`
7. `refactor(orchestrator): remove duplicate injection scan from _dispatch_tool_call`
8. `refactor: ruff fixes and update FakePolicyEngine signatures for auto_approve registry arg`

## Issues / Follow-ups

- **Ruff:** 138 pre-existing lint errors remain in the repo (line-too-long, SIM108, B008, etc.). These were not introduced by this change and should be addressed in a dedicated formatting pass.
