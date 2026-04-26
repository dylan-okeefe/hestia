# Hestia Documentation & Code Overhaul — Combined Review (April 26, 2026)

This document combines two independent evaluations of the Hestia repo on the `develop` branch:

- **Documentation and README evaluation** — structure, navigation, formatting, and reader experience across all docs.
- **Code-level re-evaluation** — a follow-up audit of code quality, decomposition, and outstanding bugs after the v0.10.0 work.

The intent is a single instruction file that a contributor (human or agent) can follow to bring both docs and code to release quality.

---

## Part 1 — README and Documentation Overhaul

### 1.1 Add a Table of Contents to README.md

The README is 475 lines with 15+ sections and no ToC. Add a compact, single-level ToC immediately after the status line. Don't nest subsections — keep it scannable.

Proposed ToC (after reordering per 1.2):

```markdown
## Contents

- [Who this is for](#who-this-is-for)
- [Quickstart](#quickstart)
- [Features](#features)
- [Platforms](#platforms)
- [Voice](#voice)
- [Configuration](#configuration)
- [Trust and multi-user](#trust-and-multi-user)
- [Running on your hardware](#running-on-your-hardware)
- [Giving Hestia a personality](#giving-hestia-a-personality)
- [Context budget and long sessions](#context-budget-and-long-sessions)
- [Security](#security)
- [Running as a daemon](#running-as-a-daemon)
- [CLI](#cli)
- [How a turn actually flows](#how-a-turn-actually-flows)
- [Development](#development)
- [Acknowledgments](#acknowledgments)
- [License](#license)
```

### 1.2 Reorder README Sections by Reader Priority

The current order puts "How a turn actually flows" (deep architecture internals) before the feature list, configuration, and platform setup. New users want to know what it does and how to run it before understanding the orchestrator loop.

**Current order → Proposed order:**

| # | Current | Proposed |
|---|---------|----------|
| 1 | Who this is for | Who this is for |
| 2 | Quickstart | Quickstart |
| 3 | How a turn actually flows | **Features** |
| 4 | Features | **Platforms** |
| 5 | Voice | Voice |
| 6 | Giving Hestia a personality | **Configuration** |
| 7 | Platforms | **Trust and multi-user** |
| 8 | Trust and multi-user | **Running on your hardware** |
| 9 | Context budget and long sessions | **Giving Hestia a personality** |
| 10 | Configuration | Context budget and long sessions |
| 11 | Running on your hardware | Security |
| 12 | Security | Running as a daemon |
| 13 | Running as a daemon | CLI |
| 14 | CLI | **How a turn actually flows** *(moved to end — architecture for the curious)* |
| 15 | Development | Development |
| 16 | Acknowledgments | Acknowledgments |
| 17 | License | License |

The key moves: Features and Platforms come up early (what does it do, where does it run). Configuration and hardware sizing move to the practical middle. "How a turn actually flows" moves near the end — it's excellent content, but it's for people who already care, not for first-time readers.

### 1.3 Tighten the Features Section

The Features section runs ~90 lines and includes inline config examples (reflection config block, `@tool` decorator example). These should be moved to linked guides. The README should sell each feature in 2–3 sentences and link out for setup details.

Specific actions:
- Move the `@tool` decorator example to a new `docs/guides/custom-tools.md` or into the existing runtime-setup guide, and replace with a one-liner like "Define custom tools with a `@tool` decorator — see [custom tools guide](docs/guides/custom-tools.md)."
- Move the `ReflectionConfig` code block to the existing `docs/guides/reflection-tuning.md` (it may already be there), and replace with a link.
- Consider grouping the tool table by category (filesystem, memory, email, network, orchestration) rather than a flat list.

### 1.4 Create docs/README.md — The Documentation Hub

This is the single highest-leverage addition. A reader who lands in `docs/` currently sees a flat directory listing with no explanation. Create a `docs/README.md` (under 100 lines) that maps the full documentation tree with audience labels:

```markdown
# Hestia Documentation

## For operators (setting up and running Hestia)

- **[Guides](guides/)** — step-by-step setup for runtime, voice, email, multi-user, security, and reflection.
- **[Environment Variables](guides/environment-variables.md)** — complete reference for all `HESTIA_*` env vars.
- **[Deploy](../deploy/README.md)** — systemd service templates and daemon setup.

## For contributors (understanding design and process)

- **[Architecture Decisions](DECISIONS.md)** — 33 ADRs covering every major design choice.
- **[Design Documents](design/)** — revised architecture, roadmap, and platform integration designs.
- **[Development Process](development-process/)** — Kimi loop logs, handoff docs, prompts, and reviews (internal history).

## Reference

- **[Release Notes](releases/)** — per-version changelogs with migration notes.
- **[Roadmap](roadmap/)** — deferred work and future systems planning.
- **[Security](../SECURITY.md)** — threat model, disclosure policy, and operational guidance.
- **[Testing](testing/)** — credentials setup and manual smoke-test procedures.
```

### 1.5 Add docs/guides/README.md — Suggested Reading Order

The 8 guides in `docs/guides/` cover distinct topics but have no landing page. Add a short README with a suggested reading order for a new operator:

1. `runtime-setup.md` — inference server and slot configuration
2. `environment-variables.md` — all `HESTIA_*` env vars
3. `voice-setup.md` — Whisper + Piper for Telegram voice
4. `email-setup.md` — IMAP/SMTP tool configuration
5. `multi-user-setup.md` — per-user memory scoping and trust overrides
6. `security.md` — prompt-injection scanner and egress auditing
7. `reflection-tuning.md` — background reflection loop setup
8. `telegram-conversation-audit.md` — audit logging for Telegram

### 1.6 Update UPGRADE.md

Currently covers v0.2.2 → v0.8.0 only. The project is on v0.10.0. Options:
- **Option A:** Extend the file to cover v0.8.0 → v0.9.0 → v0.10.0 with sections for each jump.
- **Option B:** Rename to `UPGRADE-v0.2.2-to-v0.8.0.md`, move to `docs/`, and create a new top-level `UPGRADE.md` that points to the release notes for incremental upgrades.

Option A is probably cleaner. The release notes in `docs/releases/` already have per-version detail; UPGRADE.md should cover the breaking changes and required actions.

### 1.7 Formatting Cleanup

- **Remove horizontal rules (`---`) between sections.** The README uses them between every section. With proper heading hierarchy, they add visual noise without aiding navigation. Remove all of them except the one after the intro/status block (which serves as a visual separator before the body).
- **Group the tool table by category.** The current flat list of 19 tools will only grow. Group by: Filesystem, Memory, Email, Network, Orchestration.
- **Verify all relative links resolve.** Spot-check that `docs/guides/...` and `docs/adr/...` links render correctly on GitHub from the README's location.

### 1.8 Add an Index or Note to docs/handoffs/

The 40 handoff files have no index (unlike ADRs which have `DECISIONS.md`). Options:
- Add a `docs/handoffs/README.md` that briefly explains what handoffs are and lists them (or notes they're chronological by loop number).
- Or add a one-line note in `docs/README.md` under the Development Process section explaining that handoffs are internal session-transition documents.

---

## Part 2 — Code-Level Findings (Copilot Re-evaluation)

This section captures the remaining code issues identified in the April 26 re-evaluation. All seven original "fix before release" items and all "address soon after" items were confirmed resolved. What follows are the genuine new findings.

### 2.1 Resolved Items (Confirmed ✅)

For the record, these are all closed:

- Blocking `socket.getaddrinfo()` — wrapped in `asyncio.to_thread`
- Sync file I/O in `read_file`/`write_file`/`list_dir` — wrapped in `asyncio.to_thread`
- Duplicate `artifact_refs` assignment in `delegate_task` — removed
- `WebSearchError` inherits `HestiaError`
- Internal `# Copilot H-X` / `# M-X` comments — fully stripped from `src/`
- `ScheduledTask` cron/fire_at invariant — `__post_init__` raises if both set
- `current_session_id` and `current_trace_store` ContextVars — consolidated in `runtime_context.py`
- Orchestrator decomposition — `TurnAssembly`, `TurnExecution`, `TurnFinalization` created (with caveats below)
- Meta-command handler extracted to `commands/meta.py`
- Scheduler tool factory repetition collapsed
- Dead legacy string-match in `classify_error` — removed
- `**kw: Any` dead-argument patterns in file tools — removed
- UTC suffix on displayed timestamps — `_format_utc()` used consistently
- Token usage visibility — `/tokens` command added
- UX improvements across `chat`/`ask` docstrings, `schedule list`, `hestia doctor`, skill index, Telegram validation, FTS5 docs, `TurnContext.session`, `cast()` cleanup

### 2.2 Remaining Bugs — Fix Before Release

#### Bug 1: `_compile_and_set_memory_epoch` defined twice

**Location:** `src/hestia/persistence/memory_epochs.py` AND `src/hestia/app.py` (line ~434).

**Problem:** Full duplicate definition. Commands correctly import from `memory_epochs.py`, but `app.py` has its own copy. They can silently diverge.

**Fix:** Delete the copy in `app.py`. Callers in `app.py` should import from `persistence/memory_epochs.py`.

#### Bug 2: `TransitionCallback` defined in two places

**Location:** `orchestrator/assembly.py` (line 26) AND `orchestrator/finalization.py` (line 25).

**Problem:** Same type alias defined twice. `execution.py` imports from `assembly.py`. Signature changes require two edits.

**Fix:** Move the definition to `orchestrator/types.py` (which already houses `Turn`, `TurnContext`, etc.) or a minimal `orchestrator/protocols.py`. Import from that single location everywhere.

#### Bug 3: `_sanitize_user_error` defined in two places

**Location:** `engine.py` (module-level, line 56) AND `TurnFinalization` (staticmethod, line 51).

**Problem:** Identical logic in two places. Engine methods call the module-level function; `TurnFinalization` methods call the staticmethod.

**Fix:** Pick one canonical location. Either `TurnFinalization.sanitize_user_error` (and engine imports it), or a shared utility. Delete the other.

#### Bug 4: `ScheduledTask.__post_init__` — missing "neither set" guard

**Problem:** The invariant comment says "Exactly one of `cron_expression` or `fire_at` must be set." The guard prevents both being set, but doesn't prevent *neither* being set. A `ScheduledTask` with both `None` passes validation silently and fails unpredictably at runtime.

**Fix:** Add one line:
```python
if not (bool(self.cron_expression) or bool(self.fire_at)):
    raise ValueError("Exactly one of cron_expression or fire_at must be set")
```

### 2.3 Architectural Issue — Orchestrator Decomposition Incomplete

**This is the largest remaining quality gap.**

The decomposition created three new classes (`TurnAssembly`, `TurnExecution`, `TurnFinalization`) with correct implementations. However, `Orchestrator` in `engine.py` (926 lines) still maintains its own parallel private methods for the same logic rather than delegating to them.

Specifically:
- `engine.py`'s `_run_inference_loop` (~120 lines) and `TurnExecution.run()` in `execution.py` are structurally identical — same `while` loop, same `finish_reason` branches, same policy retry logic.
- `engine.py` still contains `_execute_tool_calls`, `_execute_policy_delegation`, `_check_confirmation`, `_dispatch_tool_call`, `_scan_tool_result` — a full parallel copy of what's in `execution.py`.
- `TurnExecution` and `TurnFinalization` exist as classes but are apparently never instantiated by `Orchestrator` — it replicates their logic internally.

**Net result:** ~1,500 lines of orchestration logic across four files instead of one, with no reduction in duplication. The decomposition added abstraction without removing the original code.

**Fix:** Either:
- **(A) Complete the decomposition:** Have `Orchestrator._run_inference_loop` delegate to `TurnExecution.run()`, and delete the parallel private methods from `engine.py`. This is the intended end state.
- **(B) Roll back the decomposition:** If the phase classes aren't ready to be wired in, delete them and keep the monolithic engine until the refactor is done properly. Dead code that duplicates live code is worse than a long file.

Option A is strongly preferred — the phase classes appear correct and complete.

### 2.4 Minor Issues — Address When Convenient

#### `WebSearchError` lazy import in `classify_error`

Since `WebSearchError` now inherits from `HestiaError`, it could be added directly to the type-dispatch mapping dict, eliminating the lazy import fallback. Not a bug — just unnecessary indirection.

#### `list_dir.py` per-item `asyncio.to_thread` calls

The async fix applied `asyncio.to_thread` individually to each `is_dir()`, `is_file()`, and `stat()` call per directory entry. For large directories this means many thread-pool dispatches. More efficient to wrap the entire `iterdir()` + stat loop in a single `asyncio.to_thread` call. Performance regression, not a correctness issue.

#### `engine.py` still 926 lines

Even after completing the decomposition (2.3), audit whether `engine.py` has additional responsibilities that should move. The goal should be a ~300-line coordinator.

---

## Priority Order

For a contributor picking this up as a single work arc:

1. **Docs: Add ToC to README** (1.1) — 5 minutes, immediate value
2. **Docs: Reorder README sections** (1.2) — 15 minutes, big UX improvement
3. **Docs: Create docs/README.md** (1.4) — 15 minutes, highest-leverage docs addition
4. **Code: Fix the four bugs** (2.2) — 30 minutes total, all are small targeted fixes
5. **Docs: Tighten Features section** (1.3) — 20 minutes, may involve creating a new guide file
6. **Docs: Create docs/guides/README.md** (1.5) — 5 minutes
7. **Docs: Formatting cleanup** (1.7) — 15 minutes
8. **Code: Complete orchestrator decomposition** (2.3) — 1–2 hours, the big item
9. **Docs: Update UPGRADE.md** (1.6) — 30 minutes
10. **Docs: Index handoffs** (1.8) — 5 minutes
11. **Code: Minor cleanup** (2.4) — 15 minutes total
