# Hestia Phase 6 Report — Hardening & Observability

**Date:** 2026-04-10  
**Branch:** `feature/phase-6-hardening`  
**Status:** Complete (pending merge to `develop`)

---

## Summary

Phase 6 delivered a comprehensive hardening layer including capability-based security, path sandboxing, typed failure tracking, and CLI observability tools. This completes the foundational security model envisioned in the original design.

### Key Deliverables

1. **Capability Labels & Tool Filtering** — Tools declare security capabilities; PolicyEngine filters based on session context (subagent vs scheduler)
2. **Path Sandboxing** — File operations restricted to `allowed_roots` configuration
3. **Failure Tracking** — Typed failure classification with persistence for postmortem analysis
4. **Observability CLI** — `version`, `status`, and `failures` commands for operational visibility
5. **Centralized Logging** — Consistent logging setup across all CLI entry points

---

## Files Touched

### New Files
- `src/hestia/tools/capabilities.py` — Capability label constants
- `src/hestia/tools/builtin/path_utils.py` — Path validation utilities
- `src/hestia/errors.py` — `FailureClass` enum and `classify_error()`
- `src/hestia/persistence/failure_store.py` — `FailureBundle` and `FailureStore`
- `src/hestia/logging_config.py` — Centralized logging setup
- `tests/unit/test_tool_capabilities.py` — Capability label tests
- `tests/unit/test_path_sandboxing.py` — Path validation tests
- `tests/unit/test_failure_tracking.py` — Failure classification and store tests
- `tests/unit/test_status_queries.py` — Status command query tests
- `tests/unit/test_cli_commands.py` — CLI command tests
- `tests/unit/test_logging_config.py` — Logging setup tests
- `migrations/versions/` — Alembic migration for failure_bundles table

### Modified Files
- `src/hestia/tools/metadata.py` — Added `capabilities` field to `ToolMetadata` and `@tool` decorator
- `src/hestia/tools/builtin/*.py` — Added capability labels to all tools
- `src/hestia/tools/builtin/read_file.py` — Factory pattern with sandboxing
- `src/hestia/tools/builtin/write_file.py` — Factory pattern with sandboxing
- `src/hestia/policy/engine.py` — Added `filter_tools()` abstract method
- `src/hestia/policy/default.py` — Implemented capability-based filtering
- `src/hestia/persistence/schema.py` — Added `failure_bundles` table
- `src/hestia/persistence/sessions.py` — Added stats query methods
- `src/hestia/persistence/scheduler.py` — Added `summary_stats()`
- `src/hestia/orchestrator/engine.py` — Integrated `FailureStore`, tool chain tracking
- `src/hestia/cli.py` — Added `version`, `status`, `failures` commands; wired logging
- `src/hestia/config.py` — Added `allowed_roots` to `StorageConfig`
- `README.md` — Complete overhaul with quickstart, architecture, config reference
- `CHANGELOG.md` — Phase summaries for 1–6
- `docs/DECISIONS.md` — Added ADR-019 and ADR-020

---

## Commit SHAs (Main Ones)

Phase 6 + follow-up commits (to be filled at commit time):
- `[SHA]` — Centralized logging setup
- `[SHA]` — CLI observability commands (version, status, failures)
- `[SHA]` — Store query methods for status reporting
- `[SHA]` — README overhaul
- `[SHA]` — CHANGELOG update
- `[SHA]` — Review fixes (tool import, FTS5 wording, SQL filters)

---

## Quality Check Results

### Tests
```
pytest tests/unit/ tests/integration/ -q
# 311 passed
```

### Lint (ruff)
```
ruff check src/ tests/
# 76 errors (mostly pre-existing unused variable warnings)
# No new errors introduced in Phase 6
```

### Type Check (mypy)
```
mypy src/hestia
# 23 errors (pre-existing, mostly in Telegram adapter and scheduler)
# Phase 6 changes type-check clean
```

---

## Known Gaps / Follow-ups

### Immediate
- **Matrix Adapter** — Design doc exists at `docs/design/matrix-integration.md`, implementation pending
- **Ruff warnings** — 76 existing warnings should be cleaned up in a future housekeeping phase
- **Mypy errors** — 23 pre-existing type errors, mostly missing annotations in Telegram adapter

### Future Enhancements
- **Failure dashboard** — Web UI or CLI `failures dashboard` with filtering/aggregation
- **Alerting** — Hook failure bundles into external alerting (webhook, email)
- **Retry policies** — Some `FailureClass` types could have automatic retry with backoff
- **Metrics export** — Prometheus/OpenTelemetry integration for operational monitoring

---

## Deployment Notes

### Database Migration
Existing databases need the `failure_bundles` table:
```bash
alembic upgrade head
```

### Configuration Changes
Add `allowed_roots` to your `StorageConfig`:
```python
storage=StorageConfig(
    allowed_roots=[".", "/home/user/documents"],  # Paths read_file/write_file can access
)
```

### New CLI Commands
```bash
hestia version                    # Show version info
hestia status                     # System status summary
hestia failures list [--limit N]  # List recent failures
hestia failures summary [--days]  # Failure counts by class
```

---

## Sign-off

Phase 6 hardening is complete. The codebase now has:
- ✅ Capability-based security model
- ✅ Path sandboxing for filesystem operations
- ✅ Typed failure tracking with persistence
- ✅ CLI observability tools
- ✅ Comprehensive documentation (README, CHANGELOG, ADRs)

**Next Phase Recommendations:**
1. Matrix adapter implementation (see design doc)
2. Housekeeping: address ruff/mypy warnings
3. v0.2 release preparation

---

*Report generated: 2026-04-10*
