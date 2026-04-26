# Hestia

A personal AI assistant that runs entirely on your own hardware.

Hestia is a local-first agent for self-hosters. It talks to [llama.cpp](https://github.com/ggerganov/llama.cpp) over HTTP, stores everything in SQLite, and gives you tool use, long-term memory, scheduled tasks, and multi-platform chat (CLI, Telegram, Matrix) — including voice messages on Telegram — all from one Python process.

No cloud APIs. No telemetry. No subscriptions. Your conversations never leave the machine.

This project came out of my experience wrestling with using/modifying [**Hermes**](https://github.com/nousresearch/hermes-agent) with the constraints of running the LLM it used on my local hardware. That being said, I'm really impressed with the project, and you should absolutely check it out, especially if you're looking for an agentic harness that you can drop a frontier API into.

**Status:** v0.10.0 (April 2026). Core is stable; Telegram, Matrix, CLI, email, scheduler, memory, and voice messages all work. Actively developed.

---

## Who this is for

Hestia is built for people who run their own infrastructure. If you already have a GPU sitting idle, or you run things like Home Assistant, Synapse, or Jellyfin, Hestia fits into that world. It is for people who want an assistant that lives on their hardware, respects their privacy, and can be extended with Python.

You probably do not want Hestia if you are looking for a plug-and-play ChatGPT replacement, a multi-tenant SaaS, or a coding agent. There are better tools for all three.

---

## Quickstart

Hestia connects to a llama.cpp server for inference. Start that first:

```bash
llama-server -m your-model.gguf -c 16384 -np 4 --slot-save-path ~/.cache/hestia/slots --port 8001
```

Then install and run Hestia:

```bash
git clone https://github.com/dylanokeefe/hestia.git
cd hestia
uv sync
hestia init
hestia chat          # REPL with persistent session
```

For Telegram, Matrix, or daemon use, copy `deploy/example_config.py` to `config.py`, fill in your bot token and model name, and run `hestia --config config.py telegram` (or `matrix`). See [Running on your hardware](#running-on-your-hardware) for GPU sizing and llama-server flags.

```bash
hestia ask "What is the capital of France?"   # Single-shot, no persistence
```

---

## How a turn actually flows

When you send Hestia a message, seven things happen:

**Context assembly.** Hestia loads conversation history from SQLite, counts real tokens against llama.cpp's `/tokenize` endpoint, and trims old messages to fit the context window. Your compiled identity (from `SOUL.md`) is prepended.

**Tool selection.** Instead of describing every tool on every turn, Hestia exposes two meta-tools: `list_tools` and `call_tool`. The model asks what's available when it needs to, and calls by name. Saves roughly 2,900 tokens per request compared to enumerating the full toolset.

**Inference.** The assembled context goes to your local llama.cpp server. Hestia manages KV-cache slots so resuming a conversation skips prompt re-ingestion — a warm session restores from disk in ~200ms.

**Tool execution.** If the model asks to call a tool, Hestia runs it, appends the result to the conversation, and continues the loop until the model produces a final text response or hits the iteration limit. Dangerous tools like `write_file` and `terminal` require explicit approval.

**Overflow handling.** Tool outputs that are too large for context are auto-saved as **artifacts** — files on disk with a short handle like `art_a7f3b2c9d1`. A preview enters the conversation; the model can `read_artifact` when it needs the full content.

**Memory.** The model can save facts and search them later, backed by SQLite's FTS5 full-text search. No embeddings, no vector DB, no external services. It is just text search that works, scoped per user.

**Response.** Final text goes back to whatever platform you called in from — CLI, Telegram message, Matrix reply, or Telegram voice note.

---

## Features

### Multi-turn chat with session resume

Conversations are persisted in SQLite. Sessions resume across restarts, and if your llama.cpp server has KV-cache slot save/restore enabled, resuming is near-instant. Per-slot KV-cache checkpoints live under `slots/`.

### Tools

Nineteen built-ins plus a `@tool` decorator for writing your own:

| Tool | What it does | Confirm? |
|------|-------------|----------|
| `current_time` | Returns current date/time | No |
| `read_file` / `list_dir` | Sandboxed filesystem reads | No |
| `write_file` | Sandboxed file write | Yes |
| `terminal` | Shell command | Yes |
| `http_get` | HTTP GET; blocks private IPs (SSRF) | No |
| `read_artifact` | Retrieve an artifact by handle | No |
| `search_memory` / `save_memory` / `list_memories` | Long-term memory | No |
| `delegate_task` | Spawn a subagent session | No |
| `email_list` / `email_read` / `email_search` | IMAP reads | No |
| `email_draft` / `email_move` / `email_flag` | IMAP mutations | No |
| `email_send` | SMTP send | Yes |
| `web_search` | Tavily search (when configured) | No |

Tools declare capabilities (`read_local`, `write_local`, `shell_exec`, `network_egress`, `memory_read`, `memory_write`, `orchestration`). The policy engine uses these to restrict access by context — subagents cannot shell, scheduled tasks cannot write files by default.

Writing your own:

```python
from hestia.tools.metadata import tool

@tool(
    name="weather",
    public_description="Get weather for a location",
    capabilities=["network_egress"],
)
async def get_weather(location: str) -> str:
    return f"Weather for {location}: sunny, 22C"
```

Register it at config build time and the model sees it in `list_tools`.

### Long-term memory (user-scoped)

The model can save notes and search them. Memory rows are keyed by `(platform, platform_user)`, so each user sees only their own memories. Scheduler tasks inherit the creator's identity, so background reminders run under the right scope.

### Scheduled tasks

Cron expressions and one-shot timers. The model can create schedules via tool call, and you can manage them with `hestia schedule {add,list,run,enable,disable,remove}`. Scheduled turns go through the same orchestrator as interactive chat, with a restricted tool set (no shell, no write, no email-send by default).

### Subagent delegation

Complex tasks can be offloaded to a separate session with its own context window. The parent gets back a short summary (~300 tokens) instead of the full tool chain, keeping context growth bounded.

### Artifacts

Large tool outputs (files, HTTP bodies, command output) are auto-saved to `artifacts/` and replaced in-chat with `[art_handle] preview...`. The model calls `read_artifact` when it needs the full content. Keeps conversations focused without losing data.

### Reflection loop (opt-in)

When enabled, Hestia reviews recent traces during idle hours and proposes concrete improvements — "user corrected timezone formatting 3 times → add `preferred_timezone` to SOUL.md" or "`read_file` → `search_memory` → `save_memory` chain appeared 8 times → register a `research_and_remember` chain." Proposals are **never** auto-applied; they queue for operator review via `hestia reflection {list,show,accept,reject,defer}`.

Config:

```python
from hestia.config import HestiaConfig, ReflectionConfig

config = HestiaConfig(
    reflection=ReflectionConfig(
        enabled=True,
        cron="0 3 * * *",
        idle_minutes=15,
        lookback_turns=100,
        proposals_per_run=5,
    ),
)
```

See [reflection-tuning.md](docs/guides/reflection-tuning.md) and [ADR-018](docs/adr/ADR-018-reflection-loop-architecture.md).

### Style profile (opt-in)

Hestia can learn *how* you prefer to communicate without touching your identity document. It tracks median response length, vocabulary formality, top topics, and activity windows — all locally in SQLite. When activated, a short `[STYLE]` addendum is injected into the system prompt. Controlled via `hestia style {show,reset,disable}`. See [ADR-019](docs/adr/ADR-019-style-profile-vs-identity.md).

### Skills (experimental preview)

A framework for defining multi-step workflows as decorated Python functions. Skills declare required tools and capabilities and can be indexed into the system prompt. The framework is functional but not yet invoked automatically; opt in with `HESTIA_EXPERIMENTAL_SKILLS=1` to build your own. A `run_skill` meta-tool and a built-in skill library are planned. See [ADR-024](docs/adr/ADR-024-skills-user-defined-python-functions.md).

---

## Voice

Hestia can receive and reply with voice messages on Telegram. You record a voice note, Hestia transcribes it with Whisper, runs the turn normally, synthesizes the reply with Piper, and sends a voice note back. All inference is local.

Enable in config:

```python
config = HestiaConfig(
    telegram=TelegramConfig(
        bot_token=os.environ["HESTIA_TELEGRAM_TOKEN"],
        allowed_users=["<your-telegram-user-id>"],
        voice_messages=True,
    ),
)
```

Install the voice extra (`uv sync --extra voice`), put ffmpeg on your PATH (`sudo apt install ffmpeg` or `brew install ffmpeg`), and drop a Piper voice (`en_US-amy-medium.onnx` + `.onnx.json`) into `~/.cache/hestia/voice/`. Whisper weights auto-download on first use. See [voice-setup.md](docs/guides/voice-setup.md) for the complete walkthrough.

Replies that exceed Telegram's 1 MB voice-note limit are iteratively shortened and the full text is posted as a follow-up so nothing is silently dropped. Destructive tools still use the inline-keyboard confirmation; verbal confirmation is not in scope.

Discord voice was attempted as part of the v0.9.x arc and shelved due to DAVE E2EE complexity. The live-call story stays in Telegram territory for now.

---

## Giving Hestia a personality

Create `SOUL.md` in your project root. The default system prompt is "You are a helpful assistant." — you can do better:

```markdown
# Hestia

You are Hestia, a personal assistant running on Dylan's home server.

## Personality
- Warm but not saccharine. Helpful without being performatively eager.
- Direct. If something won't work, say so.
- You have opinions about technology. Share them when asked.
- You don't use emoji unless the human does first.

## Things you know about your human
- Runs Ubuntu on an RTX 3060. Respects the hardware budget.
- Prefers straightforward answers over hedged corporate-speak.
- Works on software projects. Familiar with Python, git, Linux.

## Things you don't do
- You don't pretend to have feelings you don't have.
- You don't apologize for things that aren't your fault.
- You don't pad responses with filler.
```

Hestia compiles the soul document into a compact identity view (bounded by `IdentityConfig.max_tokens`, default 300) cached under `.hestia/compiled_identity.txt`. Keep the soul short (under ~1000 words) and put the most important traits first. Override via `identity=IdentityConfig(soul_path=Path("deploy/SOUL.md"))`, disable with `soul_path=None`, or set `HESTIA_SOUL_PATH` in the environment.

---

## Platforms

**CLI** — the development interface. `hestia chat` is the REPL; `hestia ask "question"` is a one-shot. Best for building tools and debugging.

**Telegram** — the mobile interface. Long-polling bot with rate-limited status messages ("Thinking…", "Running search_memory…"), HTTP/1.1 forcing for API stability, user allow-list, and voice messages (see above).

**Matrix** — the automation interface. Matrix has proper CLI clients (`matrix-commander`, `matrix-nio`), so you can script conversations against Hestia, capture responses, and assert on them. That makes it the natural choice for integration tests and CI. Also fine for personal use if you already run Synapse. See [Matrix integration design](docs/design/matrix-integration.md).

**Email (tool-only)** — Hestia can read mail via IMAP and draft replies via SMTP, with send behind an explicit confirmation. See the [email-setup guide](docs/guides/email-setup.md). Note: email is a *tool* the model calls, not an inbound adapter — there is no listener on forwarded mail yet. See the roadmap for the planned inbound-email adapter.

---

## Trust and multi-user

Hestia's default posture is strict. `terminal` and `write_file` require explicit confirmation. The scheduler cannot call shell commands. Subagents cannot shell or write files. That is the right default for a fresh install but likely too restrictive for a single-operator personal deployment.

Four presets in `TrustConfig`:

- **`paranoid()`** (default) — nothing auto-approves on headless platforms.
- **`household()`** (recommended personal use) — auto-approves `terminal` and `write_file`; scheduler and subagents can shell and write.
- **`prompt_on_mobile()`** — like `household()` for background sessions, but keeps ✅/❌ confirmation prompts for `terminal`, `write_file`, and `email_send` on your phone.
- **`developer()`** — auto-approves everything. Dev/test only.

Opt in:

```python
config = HestiaConfig(
    trust=TrustConfig.household(),
)
```

Multiple users are supported with per-user memory scoping and trust overrides. Memories saved by one user are invisible to others. Platform allow-lists (Telegram `allowed_users`, Matrix `allowed_rooms`) support `fnmatch` wildcards. Grant different autonomy per person via `trust_overrides` keyed on `platform:platform_user`:

```python
config = HestiaConfig(
    trust=TrustConfig.paranoid(),
    trust_overrides={
        "telegram:<your_user_id>": TrustConfig.household(),
        "matrix:#family:example.org": TrustConfig.prompt_on_mobile(),
    },
)
```

See the [multi-user setup guide](docs/guides/multi-user-setup.md) for the full picture, including threat model and troubleshooting.

---

## Context budget and long sessions

The context window is divided into three tiers: the **per-slot budget** (`InferenceConfig.context_length`, must equal llama-server's `--ctx-size / --parallel`), a **protected block** (system prompt + compiled identity + memory epoch + skill index + new user message, never dropped), and **history** (previous turns, oldest dropped first when tight).

Two opt-in features preserve continuity when history is dropped:

**History compression.** When enabled, dropped history is summarized by a quick inference call and the summary is spliced into the system prompt for that turn only.

**Session handoff summaries.** When enabled, Hestia generates a 2–3 sentence summary on session close and stores it as a memory tagged `handoff`, so the next session can find it via normal memory search.

Both default to off. `TrustConfig.household()` and `developer()` imply both on.

If the protected block alone exceeds the budget, Hestia raises a visible warning instead of silently truncating — reduce `IdentityConfig.max_tokens`, shorten `SOUL.md`, or increase `--ctx-size / --parallel`.

---

## Configuration

Config is a Python file defining a `config` variable of type `HestiaConfig`. Python rather than YAML because IDE autocompletion, type checking, and runtime secrets composition all matter more than human-readability-at-a-glance. **Treat config files as executable code — never load one from an untrusted source.**

```python
from pathlib import Path
from hestia.config import (
    HestiaConfig, InferenceConfig, SlotConfig,
    StorageConfig, TelegramConfig, TrustConfig,
)

config = HestiaConfig(
    inference=InferenceConfig(
        base_url="http://localhost:8001",
        model_name="your-model-Q4_K_M.gguf",
        default_reasoning_budget=2048,
        max_tokens=1024,
    ),
    slots=SlotConfig(
        slot_dir=Path("slots"),
        pool_size=4,
    ),
    storage=StorageConfig(
        database_url="sqlite+aiosqlite:///hestia.db",
        artifacts_dir=Path("artifacts"),
        allowed_roots=[".", "/home/user/documents"],
    ),
    telegram=TelegramConfig(
        bot_token=os.environ["HESTIA_TELEGRAM_TOKEN"],
        allowed_users=["<your-telegram-user-id>"],
        voice_messages=True,
    ),
    trust=TrustConfig.household(),
    system_prompt="You are Hestia, a helpful personal assistant.",
    max_iterations=10,
)
```

CLI flags (`--config`, `--db-path`, `--inference-url`, `--verbose`) override config values. See [`deploy/example_config.py`](deploy/example_config.py) for a fuller template.

**PostgreSQL.** SQLite is the default. For PostgreSQL: `uv sync --extra postgres`.

---

## Running on your hardware

Hestia is built for consumer GPUs. Rough sizing guide:

| VRAM | Model | Slots | Context | Experience |
|------|-------|-------|---------|-----------|
| 8 GB | 3–4B Q4 | 2 | 8K | Works, but tool chaining is limited |
| 12 GB | 7–9B Q4 | 4 | 16K | Sweet spot — Qwen 3.5 9B recommended |
| 16 GB | 9–12B Q4/Q6 | 4 | 16–24K | Comfortable; room for longer conversations |
| 24 GB | 12–14B Q6/Q8 | 4–6 | 32K | Multi-session without eviction pressure |

Static K-quants (Q4_K_M, Q6_K_M) work well. Avoid imatrix (I-) quants — they can corrupt tool-calling.

### llama-server flags

```bash
llama-server \
  -m /path/to/model.gguf \
  -ngl 99 \
  -np 4 \
  -c 16384 \
  --flash-attn \
  --cache-type-k turbo3 \
  --cache-type-v turbo3 \
  --slot-save-path /path/to/slots \
  --jinja \
  --port 8001
```

The flags that matter: `-np 4` sets four KV-cache slots (match `SlotConfig.pool_size`). `--cache-type-k turbo3` and `--cache-type-v turbo3` quantize the KV-cache to ~3 bits per value — roughly double the context for the same VRAM on RTX 30/40-series GPUs. `--slot-save-path` enables save/restore so Hestia can checkpoint and resume sessions from disk.

### What makes Hestia efficient

Real token counting via `/tokenize` — no estimates. The meta-tool pattern — two generic tools instead of eighteen on every request. KV-cache save/restore — warm sessions skip prompt re-ingestion. Automatic artifact overflow — large tool results go to disk. Truncation-first compression — oldest history is dropped at build time, not summarized in the hot path.

---

## Security

See [`SECURITY.md`](SECURITY.md) for the full policy and responsible-disclosure process. Highlights:

**Path sandboxing.** File tools can only access directories listed in `storage.allowed_roots`. Attempts to read `/etc/shadow` or write to `~/.ssh` are rejected before the tool runs.

**SSRF protection.** `http_get` blocks requests to private IP ranges (localhost, 10.x, 172.16.x, 192.168.x, 169.254.x) so the model cannot probe internal services or cloud-metadata endpoints.

**Capability labels.** Every tool declares what it can do; the policy engine restricts capabilities per context.

**Confirmation enforcement.** Dangerous tools need explicit approval. Headless mode without a callback defaults to deny unless the trust profile auto-approves.

**Prompt-injection detection.** Tool results are scanned for known injection patterns and flagged (never blocked) before reaching the model.

**Egress auditing.** Every outbound HTTP request is logged. `hestia audit egress --since=7d` shows domain-level aggregates.

**User allow-lists.** Telegram and Matrix adapters default-deny. Empty allow-list means no one gets in.

**Config file execution.** Config files are Python modules loaded via `importlib`. That is intentional — it lets you compute values and import secrets from the environment — but treat them like any executable script. Never load a config file from an untrusted source.

---

## Running as a daemon

The `deploy/` directory contains systemd templates:

| File | Purpose |
|------|---------|
| `hestia-llama.service` | llama.cpp inference server on port 8001 |
| `hestia-agent.service` | Hestia agent (bot + scheduler) |
| `hestia-llama.alt-port.service.example` | Second llama.cpp on port 8002 |
| `install.sh` | Copies services to `/etc/systemd/system/` |
| `example_config.py` | Config template |

Quick start:

```bash
sudo deploy/install.sh $USER
sudo systemctl enable --now hestia-llama@$USER
sudo systemctl enable --now hestia-agent@$USER
```

`hestia-agent` depends on `hestia-llama`, so systemd starts them in order and restarts on failure. For per-user systemd, swap `sudo` for `--user`. Configure secrets via environment variables (`HESTIA_TELEGRAM_TOKEN`, `EMAIL_APP_PASSWORD`, etc.) so they never live in source control. See [`deploy/README.md`](deploy/README.md) for the full operator walkthrough.

---

## CLI

```
hestia [--config PATH] [--db-path PATH] [--inference-url URL] [--model NAME] [-v] COMMAND

Core:
  chat                 Interactive REPL (persistent session)
  ask MESSAGE          Single-shot query (no session persistence)
  init                 Set up DB, artifacts, slots
  health               Check llama.cpp server
  doctor               Run self-checks
  status               System overview
  version              Version info

Platforms:
  telegram             Run as Telegram bot (text + voice if enabled)
  matrix               Run as Matrix bot

Memory:
  memory {search,list,add,remove}

Scheduler:
  schedule {add,list,run,enable,disable,remove,daemon}

Reflection (opt-in):
  reflection {status,list,show,accept,reject,defer,run,history}

Style (opt-in):
  style {show,reset,disable}

Ops:
  failures {list,summary}
  audit egress --since=7d
```

Run `hestia <command> --help` for flags on any specific command.

---

## Development

```bash
uv sync                                          # install deps
uv run pytest tests/unit/ tests/integration/ -q  # tests
uv run ruff check src/ tests/                    # lint
uv run ruff format src/ tests/                   # format
uv run mypy src/hestia                           # type check
```

**Branch model.** `main` holds tagged releases; `develop` is the integration branch; feature work lives on `feature/<slug>`; release stabilization on `release/<version>`; urgent fixes on `hotfix/<slug>` off `main`.

**Architecture decisions.** 20+ ADRs in [`docs/DECISIONS.md`](docs/DECISIONS.md) covering everything from why it is called Hestia to why FTS5 over vector search to how the Discord voice E2EE story ended.

---

## Acknowledgments

Hestia exists because [**Hermes**](https://github.com/nousresearch/hermes-agent) came first.  

Built with and indebted to:

- [llama.cpp](https://github.com/ggerganov/llama.cpp) for local inference.
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) for STT.
- [Piper](https://github.com/rhasspy/piper) for TTS.
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) and [matrix-nio](https://github.com/matrix-nio/matrix-nio) for platform adapters.
- [aiosqlite](https://github.com/omnilib/aiosqlite), [SQLAlchemy](https://www.sqlalchemy.org/), and SQLite's FTS5 for persistence and search.

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
