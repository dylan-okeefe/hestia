# Hestia

A local-first personal assistant framework for people running their own LLMs on consumer hardware.

Hestia is designed for self-hosters who want a capable AI agent without sending
conversations to the cloud. It runs on a single GPU (8–24 GB VRAM), talks to
llama.cpp over HTTP, and gives you tool use, scheduled tasks, long-term memory,
and multi-platform chat — all from one process with a SQLite database.

No LangChain. No transformers. No vector DB. Just Python, llama.cpp, and SQLite.

**Status:** Pre-release — core features are functional, APIs are stabilizing.
Matrix adapter is in active development.

---

## Who this is for

- Self-hosters with 8–24 GB VRAM who want a real agent on their own hardware
- Privacy-focused users who don't want conversations leaving their machine
- Tinkerers who want to extend their assistant with custom Python tools
- People already running things like Home Assistant or Synapse who want an LLM
  that fits into that workflow

## Who this isn't for

- Plug-and-play OpenAI API wrappers (use anything else)
- Multi-tenant deployments (use letta / agno / autogen)
- Code-focused agents (use aider / opencode / SWE-agent)
- People who need a web UI (Hestia is CLI + Telegram + Matrix)

---

## Quickstart

```bash
git clone https://github.com/dylanokeefe/hestia.git
cd hestia
uv sync

# Initialize database and directories
hestia init

# Start chatting
hestia chat
```

That's it for local CLI use with default settings (connects to llama.cpp on
`localhost:8001`).

For production or Telegram deployment, create a config file:

```bash
cp deploy/example_config.py config.py
# Edit config.py — set your model, paths, Telegram token, etc.
hestia --config config.py telegram
```

See [`deploy/`](deploy/) for systemd service templates and production setup.

---

## What Hestia can do

| Feature | How it works |
|---------|-------------|
| **Multi-turn chat** | Conversation history persisted in SQLite; sessions resume across restarts |
| **Tool use** | 11 built-in tools + custom `@tool` decorator for your own |
| **Scheduled tasks** | Cron and one-shot prompts fired by the agent itself |
| **Long-term memory** | FTS5 full-text search — `save_memory`, `search_memory`, `list_memories` |
| **Subagent delegation** | Offload complex tasks to a separate session/slot with bounded context growth |
| **KV-cache management** | SlotManager with LRU eviction, save/restore to NVMe, HOT/WARM/COLD states |
| **Path sandboxing** | File tools restricted to `allowed_roots` directories |
| **Capability filtering** | Tools declare capabilities; policy engine restricts access by session type |
| **Failure tracking** | Typed `FailureClass` enum with persistence for postmortem analysis |
| **Telegram bot** | Long-polling adapter with rate-limited status edits and user allowlist |
| **Matrix bot** | *(In development)* — automation-first adapter for scripted testing and personal use |

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Platforms         CLI · Telegram · Matrix (in dev)      │
├──────────────────────────────────────────────────────────┤
│  Orchestrator      10-state turn machine, tool dispatch  │
├──────────────────────────────────────────────────────────┤
│  Policy            Capability filtering, delegation,     │
│                    confirmation enforcement              │
├──────────────────────────────────────────────────────────┤
│  Tools             11 built-in + @tool decorator         │
├──────────────────────────────────────────────────────────┤
│  Context Builder   Token budgeting via /tokenize,        │
│                    two-number calibration, pair integrity │
├──────────────────────────────────────────────────────────┤
│  Inference         llama.cpp HTTP API (chat, slots,      │
│                    tokenize, health)                     │
├──────────────────────────────────────────────────────────┤
│  Persistence       SQLite · SQLAlchemy Core (async)      │
│                    Sessions · Turns · Memory · Scheduler │
│                    Failures · Artifacts                  │
└──────────────────────────────────────────────────────────┘
```

Key components:

- **Orchestrator** — 10-state turn machine (`RECEIVED` → `BUILDING_CONTEXT` →
  `AWAITING_MODEL` → `EXECUTING_TOOLS` → … → `DONE`). Platform-agnostic
  confirmation and response callbacks.
- **SlotManager** — LRU cache over llama.cpp KV-cache slots with
  HOT/WARM/COLD temperature states and disk save/restore.
- **ContextBuilder** — Token budgeting with real `/tokenize` counts, two-number
  calibration, protected regions, oldest-first truncation.
- **MemoryStore** — FTS5 full-text search over user-saved notes. No embeddings,
  no external services.
- **PolicyEngine** — Capability-based tool filtering, delegation decisions,
  retry policy. Subagents and scheduler turns get restricted tool sets.
- **Scheduler** — Cron + one-shot tasks stored in SQLite, fired through the
  same orchestrator as interactive turns.

---

## CLI reference

```
hestia [OPTIONS] COMMAND

Options:
  --config PATH           Python config file
  --db-path PATH          Override database location
  --inference-url TEXT    llama.cpp server URL
  --model TEXT            Model filename
  -v, --verbose           DEBUG logging

Commands:
  chat                    Interactive chat session
  ask MESSAGE             Single message, single response
  init                    Create database, artifacts dir, slot dir
  health                  Check llama.cpp server status

  telegram                Run as Telegram bot (blocks)

  status                  System status summary
  version                 Version info
  failures list           Recent failures
  failures summary        Failure counts by class

  memory search QUERY     Search long-term memory
  memory list             Recent memories
  memory add TEXT         Save a memory
  memory remove ID        Delete a memory

  schedule add            Add a cron or one-shot task
  schedule list           List scheduled tasks
  schedule run ID         Manually trigger a task
  schedule enable ID      Enable a disabled task
  schedule disable ID     Disable a task
  schedule remove ID      Remove a task
  schedule daemon         Run scheduler loop (blocks)
```

---

## Configuration

Config is a Python file defining a `config` variable of type `HestiaConfig`.
Python means you get IDE autocompletion, type checking, and the ability to
compute values at load time.

```python
from pathlib import Path
from hestia.config import (
    HestiaConfig, InferenceConfig, SlotConfig,
    SchedulerConfig, StorageConfig, TelegramConfig,
)

config = HestiaConfig(
    inference=InferenceConfig(
        base_url="http://localhost:8001",
        model_name="Qwen3.5-9B-UD-Q4_K_XL.gguf",
        default_reasoning_budget=2048,
        max_tokens=1024,
    ),
    slots=SlotConfig(
        slot_dir=Path("slots"),
        pool_size=4,              # match llama-server -np
    ),
    storage=StorageConfig(
        database_url="sqlite+aiosqlite:///hestia.db",
        artifacts_dir=Path("artifacts"),
        allowed_roots=[".", "/home/user/documents"],
    ),
    telegram=TelegramConfig(
        bot_token="YOUR_TOKEN",
        allowed_users=["YOUR_USER_ID"],
    ),
    system_prompt="You are Hestia, a helpful personal assistant.",
    max_iterations=10,
)
```

### Config sections

| Section | Key fields | Purpose |
|---------|-----------|---------|
| `InferenceConfig` | `base_url`, `model_name`, `default_reasoning_budget`, `max_tokens` | llama.cpp server connection |
| `SlotConfig` | `slot_dir`, `pool_size` | KV-cache slot management |
| `SchedulerConfig` | `tick_interval_seconds` | How often to check for due tasks |
| `StorageConfig` | `database_url`, `artifacts_dir`, `allowed_roots` | Database, file storage, sandboxing |
| `TelegramConfig` | `bot_token`, `allowed_users`, `rate_limit_edits_seconds` | Telegram bot settings |

CLI options (`--config`, `--db-path`, `--verbose`, etc.) override config file values.

---

## Built-in tools

| Tool | Description | Capabilities | Confirms |
|------|-------------|--------------|----------|
| `current_time` | Current date and time | — | No |
| `http_get` | Fetch URL content | `network_egress` | No |
| `list_dir` | List directory contents | `read_local` | No |
| `read_file` | Read file (sandboxed) | `read_local` | No |
| `write_file` | Write file (sandboxed) | `write_local` | **Yes** |
| `terminal` | Execute shell command | `shell_exec` | **Yes** |
| `read_artifact` | Read artifact by ID | `read_local` | No |
| `search_memory` | Search long-term memory | `memory_read` | No |
| `save_memory` | Save to long-term memory | `memory_write` | No |
| `list_memories` | List recent memories | `memory_read` | No |
| `delegate_task` | Spawn subagent | `orchestration` | No |

Tools marked **Yes** require explicit user confirmation in interactive modes.
In headless contexts (scheduler, daemon), these tools are denied.

### Custom tools

```python
from hestia.tools.metadata import tool

@tool(
    name="weather",
    public_description="Get weather for a location",
    parameters_schema={
        "type": "object",
        "properties": {"location": {"type": "string"}},
        "required": ["location"],
    },
    capabilities=["network_egress"],
)
async def get_weather(location: str) -> str:
    # your implementation here
    return f"Weather for {location}: sunny, 72°F"
```

---

## Security model

**Path sandboxing.** File operations (`read_file`, `write_file`) are restricted
to paths within `storage.allowed_roots`. Attempts to escape are rejected before
the tool executes.

**Capability labels.** Every tool declares its capabilities from a fixed
vocabulary: `read_local`, `write_local`, `shell_exec`, `network_egress`,
`memory_read`, `memory_write`, `orchestration`. The policy engine uses these to
filter tools by session type:

- **Subagent sessions** — blocked from `shell_exec` and `write_local`
- **Scheduler turns** — blocked from `shell_exec`

**Confirmation enforcement.** Tools with `requires_confirmation=True` need
explicit user approval. If no confirmation callback is available (headless
mode), the tool fails closed with an explanatory message. This is enforced on
both the direct dispatch and meta-tool (`call_tool`) paths.

**User allowlists.** Telegram and Matrix adapters support allowlists so only
authorized users/rooms can interact with the bot.

---

## Hardware guidance

Hestia is built for consumer GPUs. Here's what to expect:

| VRAM | Model size | Slots | Context | Notes |
|------|-----------|-------|---------|-------|
| 8 GB | 3–4B Q4 | 2 | 8K | Functional but limited tool chaining |
| 12 GB | 7–9B Q4 | 4 | 16K | Sweet spot — Qwen 3.5 9B recommended |
| 16 GB | 9–12B Q4/Q6 | 4 | 16–24K | Comfortable headroom |
| 24 GB | 12–14B Q6/Q8 | 4–6 | 32K | Multi-session without eviction pressure |

### Key llama-server flags

```bash
llama-server \
  -m /path/to/model.gguf \
  -ngl 99 \                         # offload all layers to GPU
  -np 4 \                           # slot count (match SlotConfig.pool_size)
  -c 16384 \                        # context length
  --flash-attn \                    # always on
  --cache-type-k q4_0 \             # KV cache quantization (saves ~4x VRAM)
  --cache-type-v q4_0 \
  --slot-save-path /path/to/slots \ # must match SlotConfig.slot_dir
  --jinja \                         # chat template support
  --port 8001
```

### What makes Hestia efficient on small hardware

- **Token budgeting via `/tokenize`** — real counts, not estimates
- **Two-number calibration** — body_factor + meta_tool_overhead compensate for
  chat template transformation
- **Meta-tool pattern** — `call_tool` + `list_tools` saves ~2,900 tokens per
  request versus exposing all tools individually
- **KV-cache save/restore** — resuming a WARM session skips prompt re-ingestion
  entirely (~200ms restore from NVMe)
- **Truncation-first compression** — drop oldest non-protected turns at build
  time, no summarization in the hot path
- **Reasoning strip** — historical `reasoning_content` stripped before the API call

---

## Deployment

See [`deploy/README.md`](deploy/README.md) for systemd service templates.

Quick version:

```bash
cp deploy/example_config.py /opt/hestia/config.py
# Edit config.py

sudo deploy/install.sh $USER
sudo systemctl start hestia-llama@$USER
sudo systemctl start hestia-agent@$USER
```

`hestia-llama.service` runs the llama.cpp inference server.
`hestia-agent.service` runs the Hestia agent (Telegram bot + scheduler daemon).

---

## Development

```bash
uv sync                                          # install deps
uv run pytest tests/unit/ tests/integration/ -q  # 311 tests
uv run ruff check src/ tests/                    # lint
uv run ruff format src/ tests/                   # format
uv run mypy src/hestia                           # type check
```

### Project structure

```
src/hestia/
├── cli.py                 # Click CLI entry point
├── config.py              # HestiaConfig dataclasses
├── errors.py              # Error types + FailureClass enum
├── logging_config.py      # Centralized logging setup
├── core/
│   ├── inference.py       # llama.cpp HTTP client
│   └── types.py           # Message, Session, ChatResponse, etc.
├── context/
│   └── builder.py         # Token budgeting + compression
├── orchestrator/
│   ├── engine.py          # Turn state machine
│   ├── transitions.py     # ALLOWED_TRANSITIONS table
│   └── types.py           # Turn, TurnState, TurnTransition
├── inference/
│   └── slot_manager.py    # KV-cache slot lifecycle
├── scheduler/
│   └── engine.py          # Cron + one-shot task loop
├── tools/
│   ├── registry.py        # ToolRegistry + meta-tool dispatch
│   ├── metadata.py        # @tool decorator, ToolMetadata
│   ├── capabilities.py    # Capability label constants
│   └── builtin/           # Built-in tool implementations
├── memory/
│   └── store.py           # MemoryStore with FTS5
├── artifacts/
│   └── store.py           # File-backed artifact storage
├── persistence/
│   ├── db.py              # Database connection
│   ├── schema.py          # SQLAlchemy table definitions
│   ├── sessions.py        # SessionStore
│   ├── scheduler.py       # SchedulerStore
│   └── failure_store.py   # FailureStore
├── platforms/
│   ├── base.py            # Platform ABC
│   ├── cli_adapter.py     # CLI adapter
│   └── telegram_adapter.py # Telegram adapter
└── policy/
    ├── engine.py           # PolicyEngine ABC
    └── default.py          # DefaultPolicyEngine
```

### Branch model

- `main` — Tagged releases only
- `develop` — Integration branch
- `feature/<slug>` — One branch per task
- `release/<version>` — Stabilization before tagging
- `hotfix/<slug>` — Urgent fixes off `main`

### Architecture decisions

20 ADRs in [`docs/DECISIONS.md`](docs/DECISIONS.md) covering naming, tooling,
persistence, calibration, state machine design, slot management, scheduling,
platform adapters, memory, delegation, security, and failure tracking.

---

## Design documentation

| Document | Purpose |
|----------|---------|
| [`docs/hestia-design-revised-april-2026.md`](docs/hestia-design-revised-april-2026.md) | Full design plan with component descriptions, divergences from original design, and implementation notes |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | All 20 architecture decision records |
| [`docs/design/matrix-integration.md`](docs/design/matrix-integration.md) | Matrix adapter design and integration test plan |
| [`docs/roadmap/future-systems-deferred-roadmap.md`](docs/roadmap/future-systems-deferred-roadmap.md) | Post-Phase 6 roadmap: knowledge architecture, skill mining, security loop |

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
