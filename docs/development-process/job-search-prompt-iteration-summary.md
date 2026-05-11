# Job Search Prompt Iteration & Bug Fix Summary

**Date:** 2026-05-11  
**Session Lead:** Kimi Code CLI  
**Branch:** `feature/L162-cross-session-conversation-continuity` (main) / `feature/workflow-builder-runtime` (runtime)

---

## Executive Summary

This session pursued autonomous job-board scraping for Dylan O'Keefe using the base Qwen3.5-9B-DeepSeek-V4-Flash model. After **9 prompt iterations** and extensive tooling fixes, the model proved incapable of reliable multi-step autonomous extraction. The root cause is architectural: this reasoning-first model prioritizes analysis over action, consuming its entire token budget in reasoning rather than emitting tool calls.

**Deliverable achieved:** 15 verified jobs manually extracted and saved.  
**Services fixed:** Matrix sync loop restarted, llama service renamed for consistency.  
**Code committed:** Robust tool-call parsing, Bing search engine, `append_to_file` tool, orchestrator resilience improvements.

---

## 1. The Core Problem

### 1.1 Model Architecture Limitation
The Qwen3.5-9B-DeepSeek-V4-Flash is a *reasoning-first* model. When given a multi-step task with unstructured data:

- It successfully fetches data (proven in v7/v8)
- It correctly parses text output (proven in v5/v6)
- It then generates **2,000–3,500 characters of reasoning** analyzing every job in detail
- It exhausts its output token budget before emitting `append_to_file` tool calls
- Result: turn ends with empty response → retry → "max attempts exceeded"

### 1.2 Meta-Tool Fallback
Despite explicit instructions ("Do NOT use list_tools or describe_tool"), the model falls back to `list_tools` when uncertain. This is deeply ingrained training behavior that prompt engineering alone cannot override.

### 1.3 JSON Malformation
When using the `call_tool` wrapper pattern, ~50% of attempts generate unterminated JSON strings. This was mitigated in `inference.py` by gracefully skipping malformed calls, but the policy retry mechanism (max 2 attempts) still causes failure on the second malformed attempt.

---

## 2. Prompt Iterations (v1 → v9)

| Ver | Key Change | Result |
|-----|-----------|--------|
| **v1** | Basic search_web + http_get workflow | Stuck in search loops, CAPTCHA walls |
| **v2** | Anti-loop, anti-meta-tool instructions | Slightly better, still blocked |
| **v3** | Direct job board URLs | Still used http_get → unreadable JS |
| **v4** | Fixed search_web note | DuckDuckGo fully CAPTCHA'd |
| **v5** | **Bing engine swap** in search_web.py | General search works; job deep links still blocked |
| **v6** | browser_get emphasis + parsing guides | Model confused by "DO NOT call call_tool" wording |
| **v6b** | Explicit call_tool wrapper examples | Used wrapper but JSON malformed; policy retry kills turn |
| **v7** | Concise prompt + max_tokens=8192 | **browser_get direct call WORKS!** But then over-reasons, no append_to_file |
| **v8** | Direct tool call emphasis | browser_get works → list_tools fallback → over-reasons again |
| **v9** | Scripted exact sequence | Not tested; model needs results before constructing next call |

**Best result:** v7/v8 achieved successful `browser_get` direct invocation and correct parsing. The blocker is the reasoning→action gap, not tool invocation or parsing.

---

## 3. Verified Working Sources

Using `browser_get` with `wait_seconds=10`:

### Built In Boston (Primary)
- **URL:** `https://www.builtinboston.com/jobs/remote/dev-engineering?search=react&page=N`
- **Pagination:** Works (tested pages 1–5)
- **Text format:** `Company\nTitle\nReposted X Days Ago\nLocation Type\nLocation\nSalary\nLevel`
- **Parsing rule:** Company = line BEFORE "Reposted"; Title = line AFTER company

### ReactJobs.io (Secondary)
- **URL:** `https://reactjobs.io/jobs/reactjs/remote`
- **Text format:** Labeled rows (`Company`, `Location`, `Title`, `Employment Type`, `Posted`)
- **Parsing rule:** Find label → next line is value

### RemoteOK (Fallback)
- **URL:** `https://remoteok.com/remote-react-jobs`
- **Status:** Loads but text structure is loose; harder to parse reliably

---

## 4. Manual Extraction Results

**File:** `/home/dylan/Documents/Job Search/remote_software_development_jobs.md`

15 verified jobs extracted:
- **Built In Boston:** 13 jobs (Arcadia, Toast, mabl, Samsara, SoFi, Zeta Global, etc.)
- **ReactJobs.io:** 2 jobs (Mindera, Intellectsoft)

Salary ranges: $128K–$325K  
Levels: Senior, Staff, Principal, Lead  
Locations: Remote US, Remote East Coast, Hybrid Boston

**Support files created:**
- `job-board-guide.md` — Scraping guide with parsing rules for future agents
- `prompt-iteration-log.md` — Full record of all 9 prompt versions
- `model-evaluation-prompt-v{1-9}.md` — Each prompt version preserved

---

## 5. Code Changes Committed

### 5.1 Main Worktree (`feature/L162-cross-session-conversation-continuity`)

```
84a7e71 docs(skills): update hestia-orchestration skill metadata
9daa541 feat(tools): browser, memory, proposal, scheduler, style improvements
d951058 feat(orchestrator): execution resilience, policy tuning, context builder
076cf50 feat(tools): add append_to_file builtin tool
12858da fix(inference,search): robust tool-call parsing + Bing search engine
23b8f84 chore(deploy): rename hermes-llama.service to hestia-llama.service
```

**Key fixes:**
- `src/hestia/core/inference.py` — XML `<tool_call>` fallback extraction; graceful malformed JSON skip; `call_tool` wrapper unwrap
- `src/hestia/tools/builtin/search_web.py` — DuckDuckGo → Bing HTML parser; curl_cffi integration
- `src/hestia/tools/builtin/append_to_file.py` — New tool for incremental file writes
- `deploy/hestia-serve.service` — Dependency renamed to `hestia-llama.service`

### 5.2 Runtime Worktree (`feature/workflow-builder-runtime`)

```
36ebf2c docs(config): runtime README, config, matrix test script updates
6ba1fce test: update integration and unit tests for orchestrator, registry, web auth
04e73ab feat(tools): delegate_task, read_file, write_file, append_to_file wiring
0804878 feat(persistence,platforms): session handoff, slot lifecycle, telegram
ece0b71 feat(orchestrator): registry schema exposure, execution, assembly, engine
76569eb fix(inference,search): graceful malformed JSON + Bing engine swap
2bab39e chore(deploy): rename hermes-llama.service to hestia-llama.service
```

---

## 6. Infrastructure Changes

### 6.1 Service Rename: hermes-llama → hestia-llama
- **Old:** `/home/dylan/.config/systemd/user/hermes-llama.service`
- **New:** `/home/dylan/.config/systemd/user/hestia-llama.service`
- **Updated:** `deploy/hestia-serve.service` dependencies (`After=` / `Wants=`)
- **Updated:** `deploy/README.md` references
- **Status:** ✅ Active, enabled, llama-server running on :8001

### 6.2 Matrix Sync Recovery
- **Issue:** Matrix sync loop stalled after turn hit max iterations at 08:41:32 EDT
- **Symptom:** No RoomMessageText events after initial sync burst
- **Fix:** `systemctl --user restart hestia-serve.service` at 11:58:35 EDT
- **Status:** ✅ Syncing normally, 33 nio.rooms events since restart, 0 sync errors

### 6.3 Web UI Feature Flag
**Already implemented.** The web dashboard is gated by `config.web.enabled` which defaults to `False` in `WebConfig`. The `serve` command only initializes the web app when explicitly enabled:

```python
# src/hestia/commands/serve.py
if config.web.enabled:
    from hestia.web.api import create_web_app
    # ... initialize dashboard
```

The runtime config sets `web=WebConfig(enabled=True, auth_enabled=True)`, but this is a deployment choice. The default is safe for release.

**No additional feature flag work needed.**

---

## 7. Recommended Next Steps

### Path A: Composite Tool (Recommended for Autonomy)
Create a single `scrape_builtin_boston(query, page)` tool that:
1. Calls `browser_get` internally
2. Parses text into structured JSON
3. Returns a list of job dicts

The model then only needs to call **one tool** and append results. This eliminates the multi-step chaining that triggers reasoning overflow.

### Path B: Non-Reasoning Model
Switch to a non-reasoning model for this workflow:
- NSC-ACE-SABER (already evaluated — 0 jobs, but uses ONLY meta-tools)
- Granite-4.1 or other non-reasoning variants
- These models may not over-reason but have other limitations

### Path C: Hybrid Human-in-the-Loop
Use the model for discovery (fetch + parse) but have the user confirm each job before appending. This sidesteps the append-loop problem.

### Path D: Scheduled Scraping
Run a standalone Python script (not an agent) that scrapes the boards nightly and updates the file. No LLM needed for structured extraction.

---

## 8. Models Evaluated (Historical Record)

| Model | Size | Jobs Found | Blocker |
|-------|------|-----------|---------|
| Qwen3.5-9B-DeepSeek-V4-Flash (base) | 6.2GB | **4** (historical best) | Reasoning overflow on multi-step tasks |
| NSC-ACE-SABER Q4 | ~6GB | 0 | Meta-tool only pattern; burns 2+ iterations per call |
| NSC-ACE-SABER Q5 | ~7GB | 0 | Same as Q4 |
| GLM-4.6V-Flash | 6.2GB | 0 | Infinite reasoning loops; vision-first model, weak text QA |
| Ministral-3-8B-Reasoning | 5.3GB | 0 | Meta-tool only; asks user for direction |

**Conclusion:** Base Qwen remains the best performer, but its reasoning architecture is fundamentally mismatched with multi-step agentic workflows requiring rapid action.

---

## 9. Files of Record

- `/home/dylan/Documents/Job Search/remote_software_development_jobs.md` — 15 verified jobs
- `/home/dylan/Documents/Job Search/job-board-guide.md` — Scraping guide
- `/home/dylan/Documents/Job Search/prompt-iteration-log.md` — Full iteration history
- `/home/dylan/Documents/Job Search/model-evaluation-prompt-v{1-9}.md` — All prompt versions
- `/home/dylan/Hestia/docs/development-process/job-search-prompt-iteration-summary.md` — This document

---

*End of summary.*
