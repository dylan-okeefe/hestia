# Hestia — Phase 8+ Roadmap: Identity, Infrastructure, and Future Systems

> Covers items 8–16+ from the April 12 review, with decisions made and implementation details.
> This is both a planning document and a reference for writing Kimi prompts.
>
> **Assumes Phase 7.5 cleanup is complete** (bugs fixed, SSRF protection, dead code removed).
> **Assumes Phase 7 Matrix adapter has landed** (or lands concurrently).

---

## Design decisions made in this document

These are decisions, not open questions. They can be revisited, but the default is to proceed as written.

1. **Personality lives in `soul.md`, compiled to a bounded identity view on startup.** Not embedded in config, not free-form in the system prompt.
2. **Memory epochs are the priority knowledge-architecture feature.** Knowledge Router is deferred until there's enough complexity to justify it.
3. **Reasoning budget is wired through the policy engine.** No more hardcoded 2048.
4. **The CLI context dict becomes a typed dataclass.** Orchestrator construction is extracted to a helper.
5. **Bare exceptions are narrowed to specific types.** No new bare catches allowed.
6. **Datetime is UTC internally, local only at display boundaries.** Naive datetimes are a bug.
7. **Matrix is the integration test transport.** End-to-end tests run through Matrix, not mocked orchestrators.
8. **Skills start as user-defined, not auto-mined.** Skill lifecycle (draft/tested/trusted) ships before any automatic discovery.
9. **Security auditing starts as a CLI command, not a daemon.** `hestia audit` runs deterministic checks on demand.
10. **Trace store ships before failure analyst or skill miner.** You can't analyze what you don't record.
11. **Future systems (skill mining, adversarial eval, policy synthesis, auto-healing) are deferred until there's enough usage data to drive them.** They remain in the roadmap doc, not in active planning.

---

## Phase 8: Identity and orchestrator cleanup

> **Goal:** Give Hestia a personality. Clean up the CLI and policy wiring so the codebase is maintainable before adding more features.

### 8.1 — Compiled identity view (SOUL.md)

**Concept:** The user writes a `soul.md` file describing who Hestia is — tone, values, preferences, anti-patterns. On startup, Hestia reads this file and produces a compact "compiled identity view" that gets prepended to the system prompt. The full soul doc is never injected into context raw.

**New config fields:**

```python
@dataclass
class IdentityConfig:
    """Configuration for Hestia's personality/identity."""
    soul_path: Path | None = None           # Path to soul.md (None = no personality)
    compiled_cache_path: Path = field(
        default_factory=lambda: Path(".hestia/compiled_identity.txt")
    )
    max_tokens: int = 300                   # Hard cap on compiled view size
    recompile_on_change: bool = True        # Recompile if soul.md changes
```

Add `identity: IdentityConfig = field(default_factory=IdentityConfig)` to `HestiaConfig`.

**Compilation strategy:**

Two options, implement both, prefer deterministic:

1. **Deterministic extraction (default):** Parse the markdown. Extract text under each heading. Concatenate as a flat text block, stripping markdown syntax. If over `max_tokens`, truncate from the bottom (user puts most important stuff first). No model call needed.

2. **Model-assisted compilation (optional, on explicit flag):** On startup, if `soul.md` has changed since last compilation and the inference server is available, send the full soul doc to the model with the prompt: "Compress the following personality document into a concise identity statement under {max_tokens} tokens. Preserve all behavioral constraints. Output only the compressed text." Cache the result.

**Integration with context builder:**

In `ContextBuilder.build()`, the system message is currently constructed from the raw `system_prompt` string. Change this so:

```python
# In ContextBuilder.build() or in cli.py before calling process_turn:
effective_prompt = ""
if compiled_identity:
    effective_prompt += compiled_identity + "\n\n"
effective_prompt += system_prompt
```

The compiled identity view becomes the first thing in the system message. It stays frozen for the session (good for prefix cache).

**Files to create/modify:**
- New: `src/hestia/identity/__init__.py`, `src/hestia/identity/compiler.py`
- Modify: `src/hestia/config.py` (add IdentityConfig)
- Modify: `src/hestia/cli.py` (load and compile on startup, pass to process_turn)
- Modify: `src/hestia/context/builder.py` (accept optional identity prefix)
- New: `tests/unit/test_identity_compiler.py`

**Tests:**
- Deterministic compiler produces output under max_tokens
- Compiler handles missing soul.md gracefully (returns empty string)
- Compiler caches result and reuses when soul.md unchanged
- Compiled identity appears at start of system message in context builder output
- Large soul.md is truncated, not rejected

**ADR:** ADR-022 — Identity as a compiled, bounded, operator-owned document. Not self-evolving, not blurred with policy, not dynamic.

---

### 8.2 — Wire reasoning_budget through policy engine

**Problem:** `engine.py` line 196 hardcodes `reasoning_budget=2048` in the `chat()` call. The Turn dataclass has a `reasoning_budget` field, and `InferenceConfig` has `default_reasoning_budget`, but they're never connected.

**Fix:**

Add to `PolicyEngine` ABC:

```python
@abstractmethod
def reasoning_budget(self, session: Session, iteration: int) -> int:
    """How many reasoning tokens to budget for this inference call."""
    ...
```

Implement in `DefaultPolicyEngine`:

```python
def reasoning_budget(self, session: Session, iteration: int) -> int:
    """Use the configured default. Subagents get a smaller budget."""
    base = self._default_reasoning_budget
    if session.platform == "subagent":
        return min(base, 1024)  # subagents don't need deep reasoning
    return base
```

`DefaultPolicyEngine.__init__` should accept `default_reasoning_budget: int = 2048` (sourced from `InferenceConfig.default_reasoning_budget` in cli.py).

In `engine.py`, replace:

```python
reasoning_budget=2048,
```

with:

```python
reasoning_budget=self._policy.reasoning_budget(session, turn.iterations),
```

Also update the Turn's `reasoning_budget` field when creating the turn, so the value is persisted.

**Tests:** Policy returns smaller budget for subagent sessions. Budget value flows through to the chat call (mock inference client, check the kwarg).

---

### 8.3 — Extract CLI helper and type the context

**Problem:** The `ctx.obj` dict has 15 string-keyed entries, unpacked identically in 6+ commands, with a separate Orchestrator construction in each.

**Fix:**

Create a typed context:

```python
@dataclass
class CliAppContext:
    """Typed application context shared across CLI commands."""
    config: HestiaConfig
    db: Database
    inference: InferenceClient
    session_store: SessionStore
    context_builder: ContextBuilder
    tool_registry: ToolRegistry
    policy: DefaultPolicyEngine
    slot_manager: SlotManager
    memory_store: MemoryStore
    failure_store: FailureStore
    scheduler_store: SchedulerStore
    verbose: bool
    confirm_callback: ConfirmCallback | None = None

    async def bootstrap_db(self) -> None:
        """Connect to database and create tables."""
        await self.db.connect()
        await self.db.create_tables()
        await self.memory_store.create_table()
        await self.failure_store.create_table()

    def make_orchestrator(self) -> Orchestrator:
        """Create an Orchestrator with the current app context."""
        return Orchestrator(
            inference=self.inference,
            session_store=self.session_store,
            context_builder=self.context_builder,
            tool_registry=self.tool_registry,
            policy=self.policy,
            confirm_callback=self.confirm_callback,
            max_iterations=self.config.max_iterations,
            slot_manager=self.slot_manager,
            failure_store=self.failure_store,
        )
```

Store a single `CliAppContext` in `ctx.obj["app"]`. Each command does:

```python
app: CliAppContext = ctx.obj["app"]
app.confirm_callback = CliConfirmHandler()
await app.bootstrap_db()
orchestrator = app.make_orchestrator()
```

That replaces 15+ lines per command with 4.

**Files:** `src/hestia/cli.py` only. This is a refactor, no behavior changes.

**Tests:** Existing CLI tests should still pass. Optionally add a unit test for `CliAppContext.make_orchestrator()`.

---

### 8.4 — Narrow bare exception catches

**Problem:** 20 `except Exception` catches across the codebase, many masking specific errors.

**Fix:** Go through each one and narrow:

| Location | Current | Replace with |
|----------|---------|-------------|
| `slot_manager.py` (4 catches) | `Exception` | `httpx.HTTPError`, `OSError`, `PersistenceError` |
| `engine.py` line 110, 147, 278 (status updates) | `Exception` | `PlatformError` (new), `OSError` |
| `engine.py` line 302 (main error handler) | `Exception` | Keep as `Exception` — this is the catch-all, but log at ERROR not WARNING |
| `cli.py` (5 catches) | `Exception` | `HestiaError`, `httpx.HTTPError`, `OSError` |
| `scheduler/engine.py` line 62, 113 | `Exception` | `HestiaError`, `OSError` |
| `registry.py` line 109 | `Exception` | `TypeError`, `ValueError`, `OSError` |
| `current_time.py` line 29 | `Exception` | `KeyError`, `ValueError` (ZoneInfo errors) |
| `telegram_adapter.py` line 104 | `Exception` | `telegram.error.TelegramError` |
| `scheduler.py` line 54 | `Exception` | `ValueError` (croniter parse errors) |

Optionally create `PlatformError(HestiaError)` as a base for platform adapter errors.

**Rule going forward:** No new `except Exception` without a comment explaining why it's necessary.

---

### 8.5 — Standardize datetime handling

**Problem:** Mix of naive `datetime.now()`, ISO strings, and DateTime columns. Scheduler cron calculations will drift across DST boundaries.

**Fix:**

1. Create `src/hestia/core/clock.py`:

```python
"""Centralized time utilities."""
from datetime import datetime, timezone

def utcnow() -> datetime:
    """Return timezone-aware UTC now. Use this everywhere instead of datetime.now()."""
    return datetime.now(tz=timezone.utc)
```

2. Replace every `datetime.now()` in `src/` with `utcnow()` from this module.

3. In the scheduler cron calculation, convert UTC to local time before evaluating cron expressions, then convert back.

4. In CLI display code, convert UTC to local time at print boundaries.

**Search:** `grep -rn "datetime.now()" src/hestia/` — replace each hit.

**Tests:** Scheduler test with a cron expression that crosses a DST boundary should produce the correct next-run time.

---

## Phase 9: Matrix as test infrastructure + end-to-end tests

> **Goal:** Use Matrix to build a real integration test harness. Fill the biggest test gaps.

### 9.1 — Matrix-driven end-to-end test harness

**Concept:** Write a test helper that connects to a local Matrix/Synapse server, sends messages to Hestia as a real user, captures responses, and asserts on them. This tests the full stack: platform adapter → orchestrator → inference → tools → response.

**Implementation:**

```python
# tests/e2e/conftest.py
class HestiaMatrixTestClient:
    """Test client that talks to Hestia through Matrix."""

    def __init__(self, homeserver_url: str, room_id: str):
        self._client = AsyncClient(homeserver_url, "test-user")
        self._room_id = room_id

    async def send_and_wait(self, message: str, timeout: float = 30.0) -> str:
        """Send a message and wait for Hestia's response."""
        # Send message to room
        # Wait for response event from Hestia's user
        # Return response text

    async def send_and_collect(self, message: str, count: int = 1) -> list[str]:
        """Send a message and collect N responses (for multi-message replies)."""
```

**Prerequisites:**
- A local Synapse instance (docker-compose in `tests/e2e/docker-compose.yml`)
- Test user and room pre-created
- Hestia running with Matrix adapter pointed at the test server
- A mock llama.cpp server that returns canned responses (for deterministic tests)

**Test cases (Phase 9 minimum):**

1. Send "hello" → get a text response (basic round-trip)
2. Send "what time is it?" → response contains a time string (tool use)
3. Send "remember that my favorite color is blue" → "search for my favorite color" → response contains "blue" (memory round-trip)
4. Send a request that triggers `write_file` → confirm tool is denied in Matrix mode (no confirm callback) OR is auto-approved if a test confirm callback is wired
5. Multi-turn conversation → second message references first → context persistence works

**Files:**
- New: `tests/e2e/conftest.py`, `tests/e2e/test_basic_roundtrip.py`, `tests/e2e/docker-compose.yml`
- New: `tests/e2e/mock_llama_server.py` (simple HTTP server returning canned chat responses)

### 9.2 — Telegram adapter async tests

**Problem:** 6 tests, all synchronous, none test actual async behavior.

**Fix:** Add tests using `pytest-asyncio` that mock the `python-telegram-bot` Application:

- `test_send_message_calls_bot_send` — mock bot, verify `send_message` calls `bot.send_message(chat_id, text)`
- `test_edit_message_rate_limited` — send two edits within rate limit window, verify second is skipped
- `test_handle_message_rejected_for_disallowed_user` — verify unauthorized user gets no response
- `test_handle_message_calls_on_message_callback` — verify the callback receives (platform, user, text)
- `test_start_initializes_application` — verify polling starts
- `test_stop_shuts_down_cleanly` — verify cleanup

### 9.3 — CLI integration tests beyond --help

Add tests using Click's `CliRunner` that exercise actual command paths:

- `test_init_creates_database` — run `hestia init`, verify DB file exists
- `test_ask_with_mock_inference` — mock inference client, send a message, verify output
- `test_memory_add_and_search` — add a memory via CLI, search for it, verify found
- `test_schedule_add_and_list` — add a scheduled task, list tasks, verify it appears
- `test_health_reports_failure` — no inference server running, verify error output

---

## Phase 10: Memory epochs and compiled views

> **Goal:** Implement the highest-value idea from the future systems synthesis: prompt-facing memory is compiled once per session, not churned on every write.

### 10.1 — Memory epochs

**Concept:** When a session starts (or a slot is restored), Hestia compiles a "memory epoch" — a snapshot of the most relevant declarative memories, formatted as a compact text block. This gets included in the system message alongside the identity view. Mid-session `save_memory` calls write to the durable store but don't update the epoch until a refresh boundary.

**Why this matters:** Without epochs, every `save_memory` call would need to regenerate the memory view and invalidate the prefix cache. With epochs, the system message stays stable for the session's lifetime, and prefix caching works.

**Implementation:**

```python
@dataclass
class MemoryEpoch:
    """A compiled snapshot of relevant memories for prompt injection."""
    compiled_text: str        # The actual text included in the system message
    created_at: datetime
    memory_count: int         # How many memories were considered
    token_estimate: int       # Approximate token count
```

```python
class MemoryEpochCompiler:
    """Compiles a MemoryEpoch from the memory store."""

    def __init__(self, memory_store: MemoryStore, max_tokens: int = 500):
        self.store = memory_store
        self.max_tokens = max_tokens

    async def compile(self, session: Session) -> MemoryEpoch:
        """Compile a memory epoch for the given session.

        Strategy:
        1. Fetch recent memories (last 30 days)
        2. Fetch tag-matched memories if session has tags
        3. Deduplicate
        4. Format as compact text block
        5. Truncate to max_tokens
        """
```

**Refresh triggers:**
- New session start
- Slot restore from disk
- Explicit `/refresh` meta-command
- Session split (if/when implemented)

**NOT a refresh trigger:**
- `save_memory` during a turn
- Any mid-turn event

**Integration:**

The system message assembly order becomes:
1. Compiled identity view (from soul.md)
2. Compiled memory epoch
3. Base system prompt
4. (future: compact skill index)

**Files:**
- New: `src/hestia/memory/epochs.py`
- Modify: `src/hestia/context/builder.py` (accept optional epoch text)
- Modify: `src/hestia/cli.py` (compile epoch on session start)
- New: `tests/unit/test_memory_epochs.py`

**ADR:** ADR-023 — Memory epochs: compiled prompt-facing views refresh at controlled boundaries, not on every write. Rationale: prefix cache stability, token budget predictability, clear read/write boundaries.

---

## Phase 11: Trace store and enriched failure bundles

> **Goal:** Record structured traces of every unit of work. This is the foundation for everything in future systems — you can't analyze what you don't record.

### 11.1 — Trace store

**Data model:**

```python
@dataclass
class TraceRecord:
    id: str
    session_id: str
    turn_id: str
    started_at: datetime
    ended_at: datetime | None
    user_input_summary: str    # first 200 chars of user message
    tools_called: list[str]    # tool names in order
    tool_call_count: int
    delegated: bool
    outcome: str               # "success", "partial", "failed"
    artifact_handles: list[str]
    prompt_tokens: int | None
    completion_tokens: int | None
    reasoning_tokens: int | None
    total_duration_ms: int | None
```

**Storage:** New SQLite table `traces`. New `TraceStore` class in `src/hestia/persistence/trace_store.py`.

**Integration:** At the end of `process_turn()` in the orchestrator, after the turn completes (in the `finally` block), create and persist a trace record. This adds minimal overhead — it's a single INSERT.

**Why not just use turns?** Turns already capture state transitions, but they don't record token usage, tool call sequences, or timing in a query-friendly format. Traces are optimized for analysis; turns are optimized for state machine correctness.

**Alembic migration:** Add `traces` table.

### 11.2 — Enriched failure bundles

**Problem:** Current `FailureBundle` is minimal — just error message, failure class, severity, and tool chain. The future systems design calls for `policy_snapshot`, `slot_snapshot`, `request_summary`, and links to artifacts.

**Additions to `FailureBundle`:**

```python
# New fields:
request_summary: str       # first 200 chars of user message
policy_snapshot: str       # JSON: which tools were allowed, reasoning budget, etc.
slot_snapshot: str | None  # JSON: slot_id, temperature, session temperature
trace_id: str | None       # link to the trace record
```

**Migration:** Add columns to `failure_bundles` table.

**Integration:** When recording a failure bundle in `engine.py`, populate the new fields from the current session, policy, and slot state.

---

## Phase 12: Manual skill definitions

> **Goal:** Let users define reusable multi-step workflows. No automatic mining — that comes later. The model can suggest creating a skill, but the definition is human-authored.

### 12.1 — Skill lifecycle

Skills move through states: `draft` → `tested` → `trusted` → `deprecated` → `disabled`.

```python
class SkillState(str, Enum):
    DRAFT = "draft"
    TESTED = "tested"
    TRUSTED = "trusted"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"
```

### 12.2 — Skill definition format

Skills are Python files in a `skills/` directory, using a `@skill` decorator:

```python
from hestia.skills import skill

@skill(
    name="daily_briefing",
    description="Fetch weather, calendar, and news, then summarize.",
    required_tools=["http_get", "search_memory"],
    capabilities=["network_egress", "memory_read"],
    state=SkillState.DRAFT,
)
async def daily_briefing(context: SkillContext) -> SkillResult:
    weather = await context.call_tool("http_get", url="https://wttr.in/?format=3")
    memories = await context.call_tool("search_memory", query="morning routine")
    return SkillResult(
        summary=f"Weather: {weather}\nRelevant memories: {memories}",
        status="success",
    )
```

### 12.3 — Skill index in prompt

The model sees a compact index (not full skill bodies):

```
Available skills:
- daily_briefing: Fetch weather, calendar, and news, then summarize. [trusted, network_egress+memory_read]
- weekly_review: Summarize this week's activity from traces. [draft, memory_read]
```

A `run_skill` meta-tool lets the model invoke skills by name.

### 12.4 — Skill persistence

SQLite table `skills` with fields: id, name, description, file_path, state, capabilities (JSON), required_tools (JSON), created_at, last_run_at, run_count, failure_count.

### 12.5 — CLI commands

```
hestia skill list                   # list skills with states
hestia skill show NAME              # show skill details
hestia skill promote NAME           # advance state (draft→tested→trusted)
hestia skill demote NAME            # move back one state
hestia skill disable NAME           # disable without removing
hestia skill test NAME              # run skill in sandbox mode
```

**ADR:** ADR-024 — Skills as user-defined Python functions. Automatic discovery deferred until trace store has enough data. Skills are procedural memory with explicit trust lifecycle.

---

## Phase 13: Lightweight security auditing

> **Goal:** A `hestia audit` CLI command that runs deterministic checks. No daemon, no scheduler, no ML. Just facts.

### 13.1 — `hestia audit` command

Checks to implement:

1. **Capability audit:** For each tool, list its capabilities. For each session type (interactive, subagent, scheduler), list which tools are allowed. Flag any tool with `shell_exec` + `network_egress` (dangerous combination).

2. **Sandbox audit:** Verify all file tools use `check_path_allowed()`. List current `allowed_roots`. Flag if `.` is in allowed_roots (relative path, could resolve differently depending on cwd).

3. **Config audit:** Check for common misconfigurations — empty `allowed_users` on Telegram (anyone can talk to bot), `allowed_roots` containing `/` or home directory, missing `bot_token`.

4. **Dependency audit:** List installed packages with known vulnerabilities (if `pip-audit` or similar is available). If not available, skip with a note.

5. **Suspicious tool chain detection:** Query traces (Phase 11) for patterns like: `memory_write` after `http_get` (potential data exfiltration path), `terminal` called more than 3 times in one turn, `write_file` to a path outside `allowed_roots` (should be blocked, but check).

Output is a structured report printed to stdout or saved as an artifact.

### 13.2 — Policy snapshot tool

Add `hestia policy show` that dumps the current effective policy: which tools are available in each context, reasoning budgets, delegation thresholds, confirmation requirements.

---

## Future systems — what's explicitly deferred and why

These items from the future systems documents are sound ideas but premature for current project maturity. They remain in `docs/roadmap/future-systems-deferred-roadmap.md` and should not be scheduled until the prerequisites are met.

### Deferred: Skill Miner (automatic trace-based discovery)

**Why not now:** Requires (a) the trace store with enough data to cluster, (b) enough real usage to generate meaningful patterns, (c) a way to replay traces for testing skill proposals. Phase 12's manual skills validate the lifecycle; mining automates discovery later.

**Prerequisite:** Phase 11 trace store + 30+ days of real usage data.

### Deferred: Failure Analyst (automated postmortem)

**Why not now:** The enriched failure bundles (Phase 11) need to exist and accumulate before analysis is useful. The current failure store is too sparse for clustering.

**Prerequisite:** Phase 11 enriched bundles + enough failures to cluster (probably 50+).

### Deferred: Knowledge Router

**Why not now:** Memory epochs (Phase 10) solve the most pressing problem. The full five-store knowledge model (declarative, procedural, episodic, identity, artifacts) adds complexity that isn't justified yet. When Hestia has manual skills, traces, and enriched memories, the routing question becomes real.

**Prerequisite:** Phase 10 epochs + Phase 12 skills + real user feedback on what gets lost.

### Deferred: Bounded auto-healing

**Why not now:** Auto-healing requires: (a) a failure analyst producing proposals, (b) a staging mechanism for policy changes, (c) a rollback system, (d) health scoring. None of these exist yet.

**Prerequisite:** Failure analyst + policy snapshot/diff tooling + rollback infrastructure.

### Deferred: Adversarial evaluation

**Why not now:** Red-teaming makes sense when the security posture is stable enough to be meaningfully tested. The project is still adding basic sandboxing. Adversarial eval without a stable baseline produces noise, not signal.

**Prerequisite:** Phase 13 audit + all sandboxing gaps closed + stable tool/capability model.

### Deferred: Policy synthesis

**Why not now:** This is the capstone — generating candidate policies from traces, failures, and adversarial results. It requires everything else to be in place.

**Prerequisite:** Trace store + failure analyst + skill miner + adversarial eval + enough data.

### Deferred: Consolidation-first compression

**Why not now:** Full pre-compression extraction (scan for facts, skill deltas, episodic markers, failure signals) is a large subsystem. A simpler version for now: when context truncates, log which messages were dropped and whether they contained `save_memory` calls. If they did, the data is already durable. If they didn't, that's a signal the user might be losing context. Implement the full pipeline when the Knowledge Router exists.

**Simpler interim step (can be added anytime):** At truncation time, emit a warning log: "Dropped N messages from context. M contained tool calls, K contained memory operations." This is 10 lines of code and provides useful signal without the full extraction pipeline.

---

## Suggested Kimi prompt sequencing

Each of these is one Kimi cycle (1-2 hours). The cleanup pass (Phase 7.5) should go first since it fixes bugs. After that, the order can flex based on priorities.

| Order | Phase | Scope | Kimi prompt |
|-------|-------|-------|-------------|
| 1 | 7.5 | Bug fixes + security | `kimi-hestia-phase-7.5-cleanup.md` (already written) |
| 2 | 8a | Identity + reasoning_budget | §8.1 + §8.2 from this doc |
| 3 | 8b | CLI refactor + exceptions + datetime | §8.3 + §8.4 + §8.5 from this doc |
| 4 | 9 | Matrix e2e tests + Telegram async tests + CLI integration tests | §9.1 + §9.2 + §9.3 |
| 5 | 10 | Memory epochs | §10.1 |
| 6 | 11 | Trace store + enriched failure bundles | §11.1 + §11.2 |
| 7 | 12 | Manual skill definitions | §12.1–§12.5 |
| 8 | 13 | Security audit CLI | §13.1–§13.2 |

After Phase 13, re-evaluate. If there's enough trace data and real usage, consider scheduling Failure Analyst (D1) and Skill Miner (D2). If not, focus on user-facing improvements (more tools, better compression, UI).

---

## README update

A new `README.md` has been written separately. Key changes from the current version:
- "How it works" narrative section explaining the message flow
- Artifacts explained as automatic overflow (not just listed)
- Personality section with soul.md guidance
- Matrix elevated from "in development" to "automation and testing interface"
- Architecture diagram and developer-centric details moved to bottom
- Removed design doc links that were more internal than useful to newcomers
- Tools table rewritten with plain-language descriptions

The new README should replace the existing one after review.
