# Kimi build prompt — Hestia Phase 6: Pre-release hardening

**Target branch:** Create `feature/phase-6-hardening` from **`develop`** (must include merged Phase 5 / delegation).

**Read first:** `docs/HANDOFF_STATE.md`, `docs/DECISIONS.md`, `docs/hestia-design-revised-april-2026.md`, `docs/handoffs/HESTIA_PHASE_5_REPORT_20260410.md`.

**Quality bar:** `pytest`, `ruff check src/ tests/`, `mypy src/hestia` (fix new errors you introduce). Conventional commits; one commit per logical section where practical.

---

## §-1 — Merge baseline

Ensure your work applies on top of **`develop`** with Phase 5 merged (subagent delegation, policy-driven delegation, `delegate_task` tool). If `develop` is behind, merge or rebase before starting.

---

## §0 — Bug fixes (do these first)

### 0.1 — Fix `logger` in `cli.py`

**Problem:** `cli.py` references `logger.warning` and `logger.exception` (lines ~809, 868) but never imports `logging` or defines `logger = logging.getLogger(__name__)` at module level.

**Fix:** Add `import logging` and `logger = logging.getLogger(__name__)` near the top of `cli.py`.

### 0.2 — Fix `schedule_daemon` confirm_callback

**Problem:** `cli.py` line ~703 sets `ctx.obj["confirm_callback"] = CliConfirmHandler()` for the `schedule_daemon` command. The daemon runs headlessly — `CliConfirmHandler` reads from stdin, which would block forever or crash on a headless process. Same issue for the Orchestrator created inside `schedule_daemon`.

**Fix:** Set `confirm_callback = None` for `schedule_daemon` (same as Telegram). Tools with `requires_confirmation=True` will be denied, which is correct for unattended execution.

**Commit:** `fix(cli): add missing logger, fix schedule_daemon confirm_callback`

---

## §1 — Capability labels on tools

Add a standardized security capability model to every tool. This is the foundation for tool filtering (§2) and future security features.

### 1.1 — Add `capabilities` field to `ToolMetadata`

In `src/hestia/tools/metadata.py`:

- Add `capabilities: list[str] = field(default_factory=list)` to `ToolMetadata` (after `tags`).
- Add `capabilities: list[str] | None = None` parameter to the `@tool()` decorator, same pattern as `tags`.

### 1.2 — Define capability constants

Create `src/hestia/tools/capabilities.py`:

```python
"""Standardized capability labels for tools."""

READ_LOCAL = "read_local"
WRITE_LOCAL = "write_local"
SHELL_EXEC = "shell_exec"
NETWORK_EGRESS = "network_egress"
MEMORY_READ = "memory_read"
MEMORY_WRITE = "memory_write"
ORCHESTRATION = "orchestration"
```

### 1.3 — Label all built-in tools

Add `capabilities=[...]` to every `@tool(...)` decorator:

| Tool | Capabilities |
|------|-------------|
| `read_file` | `[READ_LOCAL]` |
| `write_file` | `[WRITE_LOCAL]` |
| `list_dir` | `[READ_LOCAL]` |
| `terminal` | `[SHELL_EXEC]` |
| `http_get` | `[NETWORK_EGRESS]` |
| `current_time` | `[]` (no sensitive capabilities) |
| `search_memory` | `[MEMORY_READ]` |
| `list_memories` | `[MEMORY_READ]` |
| `save_memory` | `[MEMORY_WRITE]` |
| `delegate_task` | `[ORCHESTRATION]` |
| `read_artifact` | `[READ_LOCAL]` |

### 1.4 — Expose in `list_tools` output

Update `ToolRegistry.meta_list_tools()` to include capabilities in the listing:

```python
f"- {n}: {m.public_description} [caps: {', '.join(m.capabilities) or 'none'}]"
```

### 1.5 — Tests

- Unit test that every built-in tool has non-None `capabilities` (can be empty list for safe tools).
- Unit test that `ToolMetadata.capabilities` defaults to `[]`.

**Commit:** `feat(tools): add capability labels to all built-in tools`

---

## §2 — Tool filtering by session context

### 2.1 — Add `filter_tools` to PolicyEngine

In `src/hestia/policy/engine.py`, add abstract method:

```python
@abc.abstractmethod
def filter_tools(
    self,
    session: Session,
    tool_names: list[str],
    registry: ToolRegistry,
) -> list[str]:
    """Filter available tools based on session context.

    Returns the subset of tool_names allowed for this session.
    """
```

### 2.2 — Implement in DefaultPolicyEngine

In `src/hestia/policy/default.py`:

```python
def filter_tools(self, session, tool_names, registry):
    from hestia.tools.capabilities import SHELL_EXEC, WRITE_LOCAL

    if session.platform == "subagent":
        blocked = {SHELL_EXEC, WRITE_LOCAL}
        return [
            name for name in tool_names
            if not (set(registry.describe(name).capabilities) & blocked)
        ]
    if session.platform == "scheduler":
        blocked = {SHELL_EXEC}
        return [
            name for name in tool_names
            if not (set(registry.describe(name).capabilities) & blocked)
        ]
    return tool_names
```

### 2.3 — Wire into the orchestrator

In `src/hestia/orchestrator/engine.py`, the meta-tool schemas and `meta_list_tools` / `meta_call_tool` dispatch need to respect filtered tools. The cleanest approach:

- In `process_turn`, after getting the session, compute `allowed_tools = self._policy.filter_tools(session, self._tools.list_names(), self._tools)`.
- Pass `allowed_tools` into the tool dispatch methods so `meta_list_tools` only shows allowed tools and `meta_call_tool` denies tools not in the allowed set.
- When `meta_call_tool` receives a tool name not in `allowed_tools`, return a `ToolCallResult` with `status="error"` and a message like `"Tool '{name}' is not available in this session context."`.

### 2.4 — Tests

- Unit test: subagent session cannot list or call `terminal` or `write_file`.
- Unit test: scheduler session cannot list or call `terminal`.
- Unit test: CLI session sees all tools.
- Verify existing orchestrator tests still pass (they use `platform="cli"` or similar).

**Commit:** `feat(policy): session-aware tool filtering with capability checks`

---

## §3 — Path sandboxing for file tools

### 3.1 — Add `allowed_roots` to StorageConfig

In `src/hestia/config.py`, add to `StorageConfig`:

```python
allowed_roots: list[str] = field(default_factory=lambda: ["."])
```

### 3.2 — Convert `read_file` and `write_file` to factories

Follow the same factory pattern as `make_save_memory_tool`. The factory receives `allowed_roots: list[str]` and creates the tool function with path validation baked in.

**`make_read_file_tool(allowed_roots: list[str])`** — resolve target path, check `resolved.is_relative_to(Path(root).resolve())` for any root. Return error string if denied.

**`make_write_file_tool(allowed_roots: list[str])`** — same check before writing.

The validation logic (shared between both):

```python
from pathlib import Path

def _check_path_allowed(path: str, allowed_roots: list[str]) -> str | None:
    """Return error message if path is outside allowed roots, else None."""
    resolved = Path(path).resolve()
    for root in allowed_roots:
        if resolved.is_relative_to(Path(root).resolve()):
            return None
    roots_str = ", ".join(allowed_roots)
    return f"Access denied: {path} is outside allowed roots ({roots_str})"
```

Put this helper in a new `src/hestia/tools/builtin/path_utils.py` or inline in each tool — your choice.

### 3.3 — Update `cli.py` registration

Replace direct `tool_registry.register(read_file)` with:
```python
tool_registry.register(make_read_file_tool(cfg.storage.allowed_roots))
tool_registry.register(make_write_file_tool(cfg.storage.allowed_roots))
```

Update `__init__.py` exports accordingly.

### 3.4 — Update `deploy/example_config.py`

Add `allowed_roots` to the example config with a sensible default (e.g. `["/home/user/data"]`).

### 3.5 — Tests

- Unit test: read_file with path inside allowed root succeeds.
- Unit test: read_file with path outside allowed root returns error.
- Unit test: write_file with path outside allowed root returns error.
- Unit test: relative paths resolved correctly.
- **Check existing read_file / write_file tests still pass** — they may need updating to use the factory or to set allowed_roots to permissive values.

**Commit:** `feat(security): path sandboxing for read_file and write_file`

---

## §4 — Failure tracking

### 4.1 — FailureClass enum

Add to `src/hestia/errors.py`:

```python
from enum import Enum

class FailureClass(str, Enum):
    CONTEXT_OVERFLOW = "context_overflow"
    EMPTY_RESPONSE = "empty_response"
    INFERENCE_TIMEOUT = "inference_timeout"
    INFERENCE_ERROR = "inference_error"
    TOOL_ERROR = "tool_error"
    PERSISTENCE_ERROR = "persistence_error"
    ILLEGAL_TRANSITION = "illegal_transition"
    MAX_ITERATIONS = "max_iterations"
    UNKNOWN = "unknown"

def classify_error(exc: Exception) -> tuple[FailureClass, str]:
    """Classify an exception into a FailureClass and severity."""
    mapping: dict[type, tuple[FailureClass, str]] = {
        ContextTooLargeError: (FailureClass.CONTEXT_OVERFLOW, "medium"),
        EmptyResponseError: (FailureClass.EMPTY_RESPONSE, "low"),
        InferenceTimeoutError: (FailureClass.INFERENCE_TIMEOUT, "medium"),
        InferenceServerError: (FailureClass.INFERENCE_ERROR, "high"),
        PersistenceError: (FailureClass.PERSISTENCE_ERROR, "high"),
        IllegalTransitionError: (FailureClass.ILLEGAL_TRANSITION, "high"),
    }
    for exc_type, (fc, sev) in mapping.items():
        if isinstance(exc, exc_type):
            return fc, sev
    error_msg = str(exc).lower()
    if "max iterations" in error_msg:
        return FailureClass.MAX_ITERATIONS, "medium"
    return FailureClass.UNKNOWN, "medium"
```

### 4.2 — FailureBundle model and store

New file `src/hestia/persistence/failure_store.py`:

```python
@dataclass
class FailureBundle:
    id: str
    session_id: str
    turn_id: str
    failure_class: str
    severity: str
    error_message: str
    tool_chain: str       # JSON list of tool names called during the turn
    created_at: datetime
```

`FailureStore` class with methods:
- `async create_table()` — create the `failure_bundles` table if not exists (raw DDL or SQLAlchemy Core).
- `async record(bundle: FailureBundle)` — insert a row.
- `async list_recent(limit: int = 20, failure_class: str | None = None) -> list[FailureBundle]` — query with optional filter.
- `async count_by_class(since: datetime | None = None) -> dict[str, int]` — aggregate counts.

### 4.3 — Add `failure_bundles` table to schema

In `src/hestia/persistence/schema.py`, add:

```python
failure_bundles = sa.Table(
    "failure_bundles",
    metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("session_id", sa.String, sa.ForeignKey("sessions.id"), nullable=False),
    sa.Column("turn_id", sa.String, sa.ForeignKey("turns.id"), nullable=False),
    sa.Column("failure_class", sa.String, nullable=False),
    sa.Column("severity", sa.String, nullable=False),
    sa.Column("error_message", sa.Text, nullable=False),
    sa.Column("tool_chain", sa.Text, nullable=False),  # JSON
    sa.Column("created_at", sa.DateTime, nullable=False),
    sa.Index("idx_failure_bundles_class", "failure_class"),
    sa.Index("idx_failure_bundles_created", "created_at"),
)
```

Generate an Alembic migration for this new table (or add it to the existing migration if easier — use your judgment on what's cleanest).

### 4.4 — Wire into orchestrator

In `src/hestia/orchestrator/engine.py`:

- Add `failure_store: FailureStore | None = None` to `__init__`.
- In the `except` block (~line 288), after `turn.error = str(e)`, if `failure_store` is not None:

```python
fc, severity = classify_error(e)
bundle = FailureBundle(
    id=uuid.uuid4().hex,
    session_id=session.id,
    turn_id=turn.id,
    failure_class=fc.value,
    severity=severity,
    error_message=str(e),
    tool_chain=json.dumps(getattr(turn, '_tool_names', [])),
    created_at=datetime.now(),
)
await self._failure_store.record(bundle)
```

Track tool names called during the turn: easiest approach is to collect tool names in `_execute_tool_calls` into a list attribute on the turn or a local variable threaded through.

- Update orchestrator construction in `cli.py` to pass `failure_store`.

### 4.5 — Tests

- Unit test: `classify_error` maps each HestiaError subclass correctly.
- Unit test: `FailureStore.record` + `list_recent` round-trip.
- Unit test: `count_by_class` returns correct aggregates.
- Integration test: orchestrator failure path records a failure bundle.

**Commit:** `feat(persistence): failure tracking with typed classification`

---

## §5 — Observability and CLI polish

### 5.1 — Centralized logging setup

Add `setup_logging(verbose: bool)` either in `src/hestia/logging_config.py` or inline in `cli.py`:

```python
import logging

def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
```

Call from the `cli()` group callback after config is loaded.

### 5.2 — `hestia status` command

New `@cli.command()` showing:
- Inference health (reuse the health check logic from `hestia health`)
- Session count (active, idle, archived) from `session_store`
- Recent turns: total, passed, failed in last 24h
- Scheduled tasks: enabled count, next due
- Failure summary: count by class in last 24h (if failure store available)

Requires adding a few query methods to `SessionStore` and `SchedulerStore` if they don't exist:
- `SessionStore.count_by_state() -> dict[str, int]`
- `SessionStore.recent_turn_stats(since: datetime) -> dict[str, int]` (counts by state)
- `SchedulerStore.summary() -> dict` (enabled count, next due)

### 5.3 — `hestia version` command

```python
@cli.command()
def version():
    """Show Hestia version."""
    from importlib.metadata import version as get_version
    click.echo(f"Hestia {get_version('hestia')}")
```

### 5.4 — Bootstrap failure_store

Update the `_bootstrap_db` helper (or equivalent) in `cli.py` to also call `failure_store.create_table()`. Add `failure_store` to `ctx.obj` so commands can access it.

**Commit:** `feat(cli): add status, version commands and centralized logging`

---

## §6 — Documentation

### 6.1 — ADR-019: Capability labels and tool filtering

Add to `docs/DECISIONS.md`:

- **ADR-019: Capability-based tool filtering**
- Context: Tools have tags but no security-oriented capability model. All tools are available to all session types.
- Decision: Add `capabilities` field to `ToolMetadata` with standardized labels. `PolicyEngine.filter_tools()` restricts tool visibility per session context.
- Consequence: Subagents and scheduled tasks get restricted tool sets by default.

### 6.2 — ADR-020: Failure tracking

- Context: Turn failures are stored as bare error strings. No classification, aggregation, or queryable history.
- Decision: Add `FailureBundle` model with typed `FailureClass` enum. Orchestrator records bundles on failure.
- Consequence: Foundation for future failure analysis, self-healing, and policy synthesis.

### 6.3 — README overhaul

Replace the current README stub with:
- What Hestia is (2-3 sentences)
- Architecture overview (text or diagram showing orchestrator → tools → inference → persistence)
- Quickstart (clone, install with `uv`, configure, run)
- Configuration reference (all `HestiaConfig` fields with types and defaults)
- Built-in tools catalog (name, description, capabilities, confirmation required)
- Security model (capability labels, path sandboxing, confirmation enforcement, tool filtering)
- Deployment (pointer to `deploy/`)
- Development (running tests, linting)

### 6.4 — CHANGELOG.md

Phase-by-phase summary (Phase 1a through Phase 6). Keep it concise — 3-5 bullets per phase.

**Commit:** `docs: ADR-019, ADR-020, README overhaul, CHANGELOG`

---

## §7 — Handoff report (required)

Write `docs/handoffs/HESTIA_PHASE_6_REPORT_<YYYYMMDD>.md` with:
- Summary of changes
- Files touched
- Commit SHAs
- `pytest` / `ruff` / `mypy` results
- Test counts
- Blockers (if any)
- Suggested next steps (future systems phases)

---

## Critical rules recap

- Do not leave §0 items silently undone; reviewer will check each.
- New config fields must be read in `cli.py` and passed to the components that use them.
- New store methods need CLI call sites and tests.
- Tool factories must update `__init__.py` exports.
- Compare Alembic / `schema.py` if you add tables.
- Update `docs/HANDOFF_STATE.md` after your session (Current Branch, Review Verdict placeholder, Git State, test counts).
- Existing tests must not regress — `read_file`, `write_file`, and other tool tests may need updating to use factory pattern or permissive `allowed_roots`.
- `confirm_callback=None` means tools requiring confirmation are **denied**, not silently run — this is correct and intentional for headless contexts.

---

**End of prompt**
