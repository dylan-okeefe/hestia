# L166 — API Tools Endpoint & Standalone Job Scraper Handoff

**Status:** Complete
**Branch:** `feature/l166-api-tools-and-job-scraper`

## Summary

1. **Added `/api/tools` endpoint** (`src/hestia/web/routes/tools.py`) that returns all registered tools with their schemas (name, description, parameters, requires_confirmation, tags).
2. **Wired the route** into `src/hestia/web/api.py`.
3. **Updated UI client** (`web-ui/src/api/client.ts`) to call the real backend endpoint and return full `ToolSchema[]` objects.
4. **Updated workflow editor hook** (`web-ui/src/hooks/useWorkflowEditor.ts`) to extract tool names from the schema response so existing dropdowns continue to work.
5. **Created standalone job scraper** (`scripts/scrape_jobs.py`) that deterministically scrapes Built In Boston (pages 1-3) and ReactJobs.io for senior React/frontend remote roles using `curl_cffi`.
6. **Added systemd units** (`deploy/hestia-job-scraper.service` + `.timer`) to run the scraper daily at 9 AM.
7. **Added tests** for the new `/api/tools` endpoint in `tests/unit/test_web_routes.py`.

## Quality gates

- `pytest tests/unit/test_web_routes.py::TestToolsRoutes -v` — **2 passed**
- `mypy scripts/scrape_jobs.py` — clean
- `ruff check scripts/scrape_jobs.py src/hestia/web/routes/tools.py src/hestia/web/api.py` — clean
- `cd web-ui && npx tsc --noEmit` — clean

## Notes

- The Hestia scheduler is prompt-based (LLM sessions), not command-based. The scraper is scheduled via systemd timer rather than the internal scheduler database. This matches the architecture and is noted in the handoff.
- Pre-existing test failures in `test_search_web_duckduckgo.py`, `test_web_auth.py`, `test_sessions.py`, and `test_orchestrator.py` are unrelated to this change.
- Scraper runtime: ~2 seconds. Output format matches `remote_software_development_jobs.md`.
