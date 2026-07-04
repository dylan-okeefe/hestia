# Kimi — current task (orchestration pointer)

**Orchestrator:** Kimi (self-orchestrating via subagents)
**Last set by:** Kimi — 2026-07-03

---

## Current tasks

Both cards are **In Review** pending Dylan approval/merge.

### #30 C2: redact workflow webhook secrets + owner-scope workflow lists
- **Branch:** `feature/c2-workflow-secret-scoping`
- **Commit:** `55198c75`
- **Fix:** redacted secret sentinel `"__redacted__"` no longer corrupts the real secret on GET→PUT round trips; frontend strips the sentinel before saving.
- **Gates:** `pytest tests/unit/test_workflow_secret_scoping.py tests/unit/test_web_routes.py` 83 passed; ruff/mypy clean.

### #31 C1/C3 security re-posture (auth loopback-guard + auto-approve guard)
- **Branch:** `feature/c1-c3-security-reposture`
- **Commit:** `b9ae8e2d`
- **Fix:** verified `_validate_web_security_posture` is already wired into `make_app` via `_validate_config_at_startup`; added `test_c1_aborts_at_make_app_startup` regression test proving the guard fires through the public startup path.
- **Gates:** `pytest tests/unit/test_config.py tests/unit/test_web_auth.py` 93 passed; ruff/mypy clean.

### Notes
- Full `pytest tests/unit/ tests/integration/` has pre-existing failures unrelated to these changes (memory-tool signature drift, etc.).
- Dylan to review/merge both branches to `develop` when ready.
