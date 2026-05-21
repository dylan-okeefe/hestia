# L166 — API Tools Endpoint & Standalone Job Scraper

**Status:** Spec only  
**Branch:** `feature/l166-api-tools-endpoint-and-job-scraper` (from `feature/workflow-builder-runtime`)  
**Depends on:** L161 (direct tool exposure)

## Intent

Two independent but high-impact items from the runtime branch review:

1. **COP-1:** The web UI has a `fetchTools()` function but no `/api/tools` backend endpoint. Tool dropdowns in the workflow editor silently return empty lists.

2. **Path D (model assessment):** The Qwen3.5-9B model cannot reliably perform multi-step autonomous job board scraping. A standalone Python script with `curl_cffi` and regex is more reliable and removes the LLM from a task where it adds no value.

## Review carry-forward

- *(none)*

## Scope

### §1 — Add `/api/tools` endpoint

In `src/hestia/web/routes/tools.py` (new file) or `src/hestia/web/routes/workflows.py`:

```python
from hestia.tools.registry import ToolRegistry

@router.get("/api/tools")
async def list_tools(registry: ToolRegistry = Depends(get_tool_registry)):
    """List all registered tools with their schemas."""
    schemas = []
    for name in registry.list_names():
        meta = registry.describe(name)
        schemas.append({
            "name": name,
            "description": meta.public_description,
            "parameters": meta.parameters_schema,
            "requires_confirmation": meta.requires_confirmation,
            "tags": meta.tags,
        })
    return {"tools": schemas}
```

Wire the route into `src/hestia/web/api.py`.

**Commit:** `feat(api): add /api/tools endpoint listing registered tools with schemas`

### §2 — Wire UI to backend endpoint

In `web-ui/src/api/client.ts`, update `fetchTools()` to call the new endpoint:

```typescript
export async function fetchTools(): Promise<ToolSchema[]> {
    const res = await fetch(`${API_BASE}/api/tools`);
    if (!res.ok) throw new Error(`Failed to fetch tools: ${res.status}`);
    const data = await res.json();
    return data.tools;
}
```

Verify that ToolCallNode and InvestigateNode populate their tool dropdowns from this endpoint.

**Commit:** `feat(web-ui): wire fetchTools() to /api/tools backend endpoint`

### §3 — Build standalone job scraper script

Create `scripts/scrape_jobs.py` — a deterministic Python script that scrapes Built In Boston and ReactJobs.io using the parsing rules already documented in `job-board-guide.md`.

```python
#!/usr/bin/env python3
"""Standalone job scraper for Dylan O'Keefe.

Usage: python scripts/scrape_jobs.py [--output FILE]
"""
import asyncio
import json
import re
from datetime import datetime
from pathlib import Path

try:
    from curl_cffi.requests import AsyncSession
except ImportError:
    raise SystemExit("curl_cffi is required. Install: uv pip install curl_cffi")

# Parsing rules from docs/job-board-guide.md
...
```

Features:
- Scrape Built In Boston pages 1–5 for React/frontend remote roles
- Scrape ReactJobs.io remote listings
- Filter for Senior/Staff/Principal level
- Output Markdown matching the existing `remote_software_development_jobs.md` format
- Run time: <30 seconds

**Commit:** `feat(tools): add standalone job scraper script`

### §4 — Add scraper to scheduler

Register the scraper as a scheduled task in `config.runtime.py` (or via the scheduler CLI):

```python
# Run daily at 9 AM
{"name": "job_scraper", "cron": "0 9 * * *", "command": "uv run python scripts/scrape_jobs.py"}
```

**Commit:** `feat(scheduler): register job scraper as daily scheduled task`

### §5 — Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia scripts/scrape_jobs.py
uv run ruff check src/ tests/ scripts/
```

## Acceptance

- `/api/tools` returns a JSON list of all registered tools with schemas
- Workflow editor tool dropdowns populate from the backend
- `scripts/scrape_jobs.py` runs successfully and produces valid Markdown
- Scraper output matches the format of `remote_software_development_jobs.md`
- Scraper is registered in the scheduler and runs on schedule
- All quality gates pass

## Handoff

- Write `docs/handoffs/L166-api-tools-endpoint-and-job-scraper-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`
