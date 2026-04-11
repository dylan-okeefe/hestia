# Hestia

A local-first personal assistant framework for people running their own LLMs on constrained consumer hardware (8–16 GB VRAM, one GPU).

Hestia is designed for self-hosters who want a capable AI assistant without sending their conversations to the cloud. It's opinionated, lightweight, and built specifically for llama.cpp. No LangChain. No transformers. No vector DB required.

**Status:** Beta — approaching v0.2. Core features are functional; APIs are stabilizing.

For detailed design documentation, see [`docs/hestia-design-revised-april-2026.md`](docs/hestia-design-revised-april-2026.md).

---

## Who This Is For

- People with 8–24 GB VRAM who want a real agent on their own hardware
- Privacy-focused users who don't want to send conversations to Claude/GPT
- Tinkerers who want to extend their assistant with custom Python tools
- Self-hosters who already run things like Home Assistant

## Who This Isn't For

- People who want plug-and-play with OpenAI API (use anything else)
- Multi-tenant deployments (use letta/agno/autogen)
- Coding-focused agents (use opencode / opendevin / aider)
- People who want a web UI (this is a chat interface via Telegram/Matrix/CLI)

---

## Quickstart

```bash
# Clone and install
git clone <repo-url>
cd hestia
uv sync

# Copy example config and customize
cp deploy/example_config.py config.py
# Edit config.py to set your paths, model, Telegram token, etc.

# Initialize database and directories
hestia init

# Start chatting (CLI mode)
hestia chat

# Or run as Telegram bot
hestia telegram
```

See [`deploy/`](deploy/) for systemd service templates and production deployment guidance.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Hestia                              │
├─────────────────────────────────────────────────────────────┤
│  Platforms         │  Telegram, Matrix (planned), CLI       │
├─────────────────────────────────────────────────────────────┤
│  Orchestrator      │  10-state turn machine, tool dispatch  │
├─────────────────────────────────────────────────────────────┤
│  Tools             │  Built-in + custom @tool decorators    │
├─────────────────────────────────────────────────────────────┤
│  Context Builder   │  Token budgeting, calibration          │
├─────────────────────────────────────────────────────────────┤
│  Inference         │  llama.cpp server via HTTP API         │
├─────────────────────────────────────────────────────────────┤
│  Persistence       │  SQLite + SQLAlchemy Core (async)      │
│                    │  Sessions, turns, scheduler, memory    │
└─────────────────────────────────────────────────────────────┘
```

Key components:
- **SessionStore**: Manages conversation sessions with HOT/WARM/COLD temperature states
- **SlotManager**: LRU cache for llama.cpp KV-cache slots with disk save/restore
- **Scheduler**: Cron and one-shot scheduled tasks
- **MemoryStore**: FTS5-based long-term memory with full-text / keyword search
- **PolicyEngine**: Capability-based tool filtering and delegation decisions

---

## Configuration

Configuration is done via a Python file defining a `config` variable of type `HestiaConfig`:

```python
from hestia.config import HestiaConfig, InferenceConfig, StorageConfig

config = HestiaConfig(
    inference=InferenceConfig(
        base_url="http://localhost:8001",
        model_name="Qwen3.5-9B-UD-Q4_K_XL.gguf",
    ),
    storage=StorageConfig(
        database_url="sqlite+aiosqlite:///hestia.db",
        allowed_roots=[".", "/home/user/documents"],  # Path sandboxing
    ),
    system_prompt="You are a helpful assistant.",
    max_iterations=10,
    verbose=False,
)
```

### Config Fields

| Field | Type | Description |
|-------|------|-------------|
| `inference` | `InferenceConfig` | llama.cpp server URL, model name, token limits |
| `slots` | `SlotConfig` | KV-cache slot directory and pool size |
| `scheduler` | `SchedulerConfig` | Tick interval for scheduled tasks |
| `storage` | `StorageConfig` | Database URL, artifacts dir, **allowed_roots** for sandboxing |
| `telegram` | `TelegramConfig` | Bot token, allowed users, timeouts |
| `system_prompt` | `str` | Default system prompt |
| `max_iterations` | `int` | Hard limit on tool loops per turn |
| `verbose` | `bool` | Enable DEBUG logging |

CLI options (`--config`, `--db-path`, `--verbose`, etc.) override config file values.

---

## Built-in Tools

| Tool | Description | Capabilities | Confirm |
|------|-------------|--------------|---------|
| `current_time` | Get current date/time | — | No |
| `http_get` | Fetch URL content | `network_egress` | No |
| `list_dir` | List directory contents | `read_local` | No |
| `read_file` | Read file contents | `read_local` | No |
| `write_file` | Write file contents | `write_local` | **Yes** |
| `terminal` | Execute shell command | `shell_exec` | **Yes** |
| `read_artifact` | Read artifact by ID | `read_local` | No |
| `search_memory` | Search long-term memory | `memory_read` | No |
| `save_memory` | Save to long-term memory | `memory_write` | No |
| `list_memories` | List recent memories | `memory_read` | No |
| `delegate_task` | Delegate to subagent | `orchestration` | No |

Tools requiring confirmation will be denied when running in headless mode (scheduler, Telegram without confirmation callback).

### Custom Tools

Add your own tools with the `@tool` decorator:

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
)
async def get_weather(location: str) -> str:
    return f"Weather for {location}: sunny, 72°F"
```

---

## Security

### Path Sandboxing

File operations (`read_file`, `write_file`) are restricted to paths within `storage.allowed_roots`. Attempts to access paths outside these roots are rejected.

### Capability Labels

Tools declare capabilities (`read_local`, `write_local`, `shell_exec`, `network_egress`, etc.). The `PolicyEngine.filter_tools()` method restricts tool availability based on session context:
- **Subagent sessions**: Blocked from `shell_exec` and `write_local`
- **Scheduler execution**: Blocked from `shell_exec`

### Confirmation Requirements

Tools marked with `requires_confirmation=True` require explicit user approval in interactive modes. In headless contexts (scheduler, daemon mode), these tools are denied with an explanatory message.

---

## Deploy

Systemd service templates are in [`deploy/`](deploy/):

- `hestia-llama.service` — llama.cpp inference server
- `hestia-agent.service` — Hestia agent (Telegram + scheduler)
- `install.sh` — Service installation script

Copy and customize for your setup. See [`deploy/README.md`](deploy/README.md) for details.

---

## Development

```bash
# Run tests
uv run pytest tests/unit/ tests/integration/ -q

# Lint
uv run ruff check src/ tests/

# Type check
uv run mypy src/hestia

# Format
uv run ruff format src/ tests/
```

### Project Structure

```
src/hestia/
├── cli.py              # CLI entry point
├── config.py           # Configuration dataclasses
├── core/               # Core types and inference client
├── context/            # Context building and token budgeting
├── inference/          # SlotManager
├── logging_config.py   # Centralized logging setup
├── memory/             # MemoryStore with FTS5
├── orchestrator/       # Turn execution engine
├── persistence/        # Database, sessions, scheduler
├── platforms/          # Telegram adapter
├── policy/             # PolicyEngine
├── scheduler/          # Scheduled task execution
└── tools/              # Tool registry and built-in tools
```

---

## Branch Model

- `main` — Released, tagged versions only. Never committed to directly.
- `develop` — Integration branch. Features merge here.
- `feature/<slug>` — One per task.
- `release/<version>` — Stabilization before a tag.
- `hotfix/<slug>` — Urgent fix off `main`.

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
