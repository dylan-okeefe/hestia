# Hestia

A personal assistant that runs entirely on your own hardware.

Hestia is a local-first AI agent for self-hosters. It runs on a single consumer GPU, talks to [llama.cpp](https://github.com/ggerganov/llama.cpp) over HTTP, and gives you tool use, long-term memory, scheduled tasks, and multi-platform chat — all from one Python process backed by SQLite.

Your conversations never leave your machine. No cloud APIs, no telemetry, no subscriptions.

**Status:** Pre-release. Core features work, APIs are stabilizing, Matrix adapter is in active development.

---

## Demo

<!-- TODO(dylan): record asciicast and replace PLACEHOLDER -->
[![asciicast](https://asciinema.org/a/PLACEHOLDER.svg)](https://asciinema.org/a/PLACEHOLDER)

<!-- TODO(dylan): capture screenshot and save to docs/assets/hestia-chat.png -->
![Chat screenshot](docs/assets/hestia-chat.png)

Text transcript:

```
$ hestia chat
You: What's the weather like today?
Hestia: I'll check that for you.
[tool call: current_time → 2026-04-18T14:32:00-04:00]
Hestia: It's 72°F and sunny in your area. Perfect day to open a window.
```

---

## Who this is for

Hestia is built for people who run their own infrastructure. If you already have a GPU sitting idle, or you're running things like Home Assistant, Synapse, or Jellyfin, Hestia fits into that world. It's for people who want an AI assistant that lives on their hardware, respects their privacy, and can be extended with Python.

You probably don't want Hestia if you're looking for a plug-and-play ChatGPT replacement, a multi-tenant deployment, or a coding agent. There are better tools for all of those.

---

## How it works

You send Hestia a message — through the terminal, Telegram, or Matrix. Here's what happens:

1. **Context assembly.** Hestia loads your conversation history from SQLite, counts the real token cost using llama.cpp's `/tokenize` endpoint, and trims old messages if needed to stay within your GPU's context window. If you've given Hestia a personality (more on that below), it gets prepended to every conversation.

2. **Tool selection.** Instead of describing every available tool to the model on every message (which wastes tokens), Hestia uses a meta-tool pattern: the model gets two generic tools — `list_tools` to see what's available, and `call_tool` to invoke one by name. This saves roughly 2,900 tokens per request compared to listing all tools individually. On a 9B model with 16K context, that's a meaningful chunk of your budget.

3. **Model inference.** The assembled context goes to your local llama.cpp server. Hestia manages KV-cache slots so that resuming a conversation doesn't require re-processing the entire history — a warm session restores from disk in about 200ms.

4. **Tool execution.** If the model asks to call a tool, Hestia executes it, adds the result to the conversation, and sends it back to the model. This loop continues until the model produces a final text response or hits the iteration limit.

5. **Overflow handling.** When a tool produces a result that's too large for context (a long file, a big HTTP response), Hestia automatically saves the full result as an **artifact** — a file on disk with a short handle like `art_a7f3b2c9d1`. Only a preview goes into the conversation, and the model can use `read_artifact` to access the full content when it needs it. This keeps your context window clean without losing data.

6. **Memory.** Hestia has a long-term memory backed by SQLite's FTS5 full-text search. The model can save facts, search for them later, and list recent memories. No embeddings, no vector database, no external services. It's just text search that works.

---

## Quickstart

### Prerequisites

Hestia connects to a [llama.cpp](https://github.com/ggerganov/llama.cpp) server for inference. Start it before running Hestia:

```bash
# Download and build llama.cpp (see their README for details)
# Then start the server with your model:
llama-server -m your-model.gguf -c 8192 --port 8001
```

Hestia connects to `http://localhost:8001` by default. See [Running on your hardware](#running-on-your-hardware) for GPU-specific options.

### Install and run

```bash
git clone https://github.com/dylanokeefe/hestia.git
cd hestia
uv sync

# Initialize database and directories
hestia init

# Start chatting (connects to llama.cpp on localhost:8001 by default)
hestia chat
```

For Telegram or production use, create a config file:

```bash
cp deploy/example_config.py config.py
# Edit config.py — set your model path, Telegram token, personality, etc.
hestia --config config.py telegram
```

---

## What it can do

**Multi-turn chat** — Conversation history is persisted in SQLite. Sessions resume across restarts. If your llama.cpp server has KV-cache slot save/restore enabled, resuming is near-instant.

**Tool use** — 11 built-in tools plus a `@tool` decorator for writing your own. Tools declare their capabilities (filesystem access, network, shell, memory) and the policy engine controls which tools are available in which contexts. Dangerous tools like `write_file` and `terminal` require explicit confirmation.

**Long-term memory** — The model can save notes and search them later using full-text search. Useful for remembering preferences, project context, recurring tasks, or anything you'd want your assistant to recall between sessions.

**Scheduled tasks** — Cron expressions and one-shot timers. The model itself can create scheduled tasks, or you can manage them through the CLI. Scheduled tasks run through the same orchestrator as interactive conversations, with a restricted tool set for safety.

**Subagent delegation** — Complex tasks can be offloaded to a separate session with its own context window. The parent session gets back a short summary (about 300 tokens) instead of the full tool chain, keeping context growth bounded.

**Artifacts** — When tool outputs are too large for the conversation (files, HTTP responses, command output), they're automatically saved to disk and replaced with a preview + handle. The model can read the full artifact when it needs to. This keeps conversations focused without losing data.

### Skills (experimental preview)

> **Preview feature:** Skills are an experimental preview. Set `HESTIA_EXPERIMENTAL_SKILLS=1` to opt in. See README.md#skills.
> Skills are not invoked during a normal turn yet — the framework lets you define and manage skills, but the orchestrator does not call them automatically.

Hestia includes a skills framework for defining multi-step workflows as decorated Python functions. Skills declare their required tools and capabilities, and can be indexed for inclusion in the system prompt.

```python
from hestia.skills import skill, SkillState

@skill(
    name="daily_briefing",
    description="Summarize today's calendar and weather",
    required_tools=["http_get", "memory_search"],
    state=SkillState.DRAFT,
)
async def daily_briefing(context):
    ...
```

This system is functional but not yet integrated into the orchestrator's tool-calling flow. A `run_skill` meta-tool and built-in skill library are planned for a future release. See [ADR-0024](docs/adr/ADR-0024-skills-user-defined-python-functions.md) for the design rationale.

### Reflection loop (opt-in)

When enabled, Hestia reviews recent conversation traces during idle hours and generates concrete improvement proposals. Proposals are **never auto-applied** — they queue for operator review and can be accepted, rejected, or deferred via CLI.

Example proposals:
- "User corrected timezone formatting 3 times → add `preferred_timezone` to SOUL.md"
- "`read_file` → `search_memory` → `save_memory` chain appeared 8 times → register a 'research_and_remember' chain"

Enable in your config:

```python
from hestia.config import HestiaConfig, ReflectionConfig

config = HestiaConfig(
    reflection=ReflectionConfig(
        enabled=True,
        cron="0 3 * * *",        # 3 AM daily
        idle_minutes=15,         # skip if session was active within 15 min
        lookback_turns=100,      # analyze last 100 traces
        proposals_per_run=5,     # max proposals per run
        expire_days=14,          # proposals expire after 14 days
    )
)
```

CLI walkthrough:

```bash
# Check pending proposal count
hestia reflection status

# List pending proposals
hestia reflection list --status pending

# Review a proposal in detail
hestia reflection show prop_abc123

# Accept, reject, or defer
hestia reflection accept prop_abc123
hestia reflection reject prop_abc123 --note "Not useful"
hestia reflection defer prop_abc123 --until 2026-05-01T00:00:00

# Manually trigger a reflection run
hestia reflection run --now

# View history
hestia reflection history
```

When pending proposals exist, Hestia injects a one-time system note at the start of the next session: "You have N pending reflection proposal(s)... summarize the top 3 and ask whether to accept/reject/defer."

See [docs/guides/reflection-tuning.md](docs/guides/reflection-tuning.md) for tuning guidance and [ADR-0018](docs/adr/ADR-0018-reflection-loop-architecture.md) for architecture rationale.

### Style profile (opt-in)

Hestia can learn *how* you prefer to communicate without modifying your identity (`SOUL.md`). The style profile tracks lightweight, observable signals per platform × user:

- **Preferred response length** — median completion tokens for turns you don't ask to shorten/lengthen
- **Formality** — ratio of technical vocabulary in your messages
- **Top topics** — most frequent memory tags in recent sessions
- **Activity window** — hour-of-day histogram of your usage

These metrics live only in your local SQLite database. They never leave the machine.

Enable in your config:

```python
from hestia.config import HestiaConfig, StyleConfig

config = HestiaConfig(
    style=StyleConfig(
        enabled=True,
        min_turns_to_activate=20,  # don't inject until enough data
        lookback_days=30,
        cron="15 3 * * *",         # 15 min after reflection run
    )
)
```

When activated, a short `[STYLE]` addendum is injected into the system prompt:

```
[STYLE] Recent tone: technical. Preferred response length: ~150 tokens.
Active topics this week: python, deployment, sqlite.
```

CLI controls:

```bash
# View current profile
hestia style show

# Wipe and relearn from scratch
hestia style reset

# Temporarily disable injection
hestia style disable
```

Style is always additive — it only appends a small addendum, never edits `SOUL.md` or memory epochs. You can reset or disable it without side effects. See [ADR-0019](docs/adr/ADR-0019-style-profile-vs-identity.md) for the design rationale.

---

## Platforms

Hestia speaks three protocols, each with a different role:

**CLI** — The development interface. `hestia chat` gives you a REPL for interactive conversations, `hestia ask "question"` for one-shots. Best for building and testing tools, debugging conversations, and daily local use.

**Telegram** — The mobile interface. Long-polling bot with rate-limited status messages ("Thinking...", "Running search_memory..."), user allowlist, and HTTP/1.1 forcing for API stability. Good for daily use when you're away from your terminal.

**Matrix** — The automation and testing interface. Matrix has proper CLI clients (`matrix-commander`, `matrix-nio`), which means you can script conversations against Hestia, capture responses, and assert on them. This makes Matrix the natural choice for integration testing, regression suites, and CI pipelines. Also works well for personal use if you already run a Synapse server.

See [Matrix manual smoke test guide](docs/testing/matrix-manual-smoke.md) for a step-by-step walkthrough, [Matrix integration design](docs/design/matrix-integration.md) for architecture details, and [Credentials and secrets](docs/testing/CREDENTIALS_AND_SECRETS.md) for bot and tester setup.

---

## Giving Hestia a personality

The default system prompt is "You are a helpful assistant." You can do better.

Create a **`SOUL.md`** file in your project root (default path: `hestia.config.DEFAULT_SOUL_MD_PATH`):

```markdown
# Hestia

You are Hestia, a personal assistant running on Dylan's home server.

## Personality
- Warm but not saccharine. You're helpful without being performatively eager.
- Direct. If something won't work, say so.
- You have opinions about technology and you're willing to share them when asked.
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

Compiled identity is on by default: `HestiaConfig` looks for **`SOUL.md`** in the process working directory. Override or disable as needed:

```python
from pathlib import Path

from hestia.config import DEFAULT_SOUL_MD_PATH, HestiaConfig, IdentityConfig

config = HestiaConfig(
    identity=IdentityConfig(
        soul_path=DEFAULT_SOUL_MD_PATH,  # explicit; same as the default
        max_tokens=300,  # Hard cap on compiled identity size
    ),
    # ... rest of config
)

# Other paths: soul_path=Path("deploy/SOUL.md")
# Disable: identity=IdentityConfig(soul_path=None)
```

You can also override the path via environment variables (useful when running
Hestia from outside the project root):

```bash
export HESTIA_SOUL_PATH=/path/to/SOUL.md
export HESTIA_CALIBRATION_PATH=/path/to/calibration.json
```

Hestia compiles your soul document into a compact identity view on startup. The full soul doc isn't injected raw — it's extracted, bounded, and cached under `.hestia/compiled_identity.txt` for efficiency. Keep the soul document reasonably short (under 1000 words). The compiled view is truncated to `max_tokens`, so put the most important traits first.

---

## Trust profiles

Hestia's default posture is strict: `terminal` and `write_file` both require
explicit user confirmation, the scheduler cannot call shell commands, and
subagents cannot shell or write files. This is safe for a fresh install, but
it's often more restrictive than you want for a single-operator personal
deployment.

Four presets live in `TrustConfig`:

- **`TrustConfig.paranoid()`** (default) — current behavior. Every `terminal`
  or `write_file` call on Telegram/Matrix/scheduler is blocked unless you wire
  a custom confirm callback. Scheduler and subagents can't shell or write.

- **`TrustConfig.household()`** (recommended for personal use) —
  auto-approves `terminal` and `write_file` on headless platforms, lets the
  scheduler run shell commands, lets subagents shell and write.

- **`TrustConfig.prompt_on_mobile()`** — like `household()` for scheduler and
  subagents, but keeps confirmation prompts for `terminal`, `write_file`, and
  `email_send` on mobile platforms. Use this when you want a ✅/❌ prompt on
  your phone for dangerous tools.

- **`TrustConfig.developer()`** — auto-approves everything. Dev/test only.

Opt in inside your `config.py`:

```python
from hestia.config import HestiaConfig, TrustConfig
config = HestiaConfig(
    ...,
    trust=TrustConfig.household(),
)
```

See `hestia config` for the active profile.

### Multi-user security

Hestia supports multiple users with per-user memory scoping and trust overrides.
Memories saved by one user are invisible to others. Platform allow-lists
(Telegram `allowed_users`, Matrix `allowed_rooms`) support wildcards (`*`, `?`).
Use `trust_overrides` keyed by `platform:platform_user` to grant different
autonomy levels to different people. See the [multi-user setup guide](docs/guides/multi-user-setup.md) for details.

---

## Context budget and long sessions

Hestia's context is divided into three tiers:

1. **Per-slot context budget** — set by `InferenceConfig.context_length` (should equal
   llama-server's `--ctx-size / --parallel`). This is the hard ceiling.
2. **Protected block** — system prompt + compiled identity + memory epoch + skill index
   + the new user message. This block is never dropped.
3. **History** — previous turns. Oldest messages are dropped first when the budget
   is tight.

When history is dropped, it is gone from the model's view for that turn. Two
opt-in features help preserve continuity:

### History compression

When enabled, dropped history is summarized by a quick inference call and the
summary is spliced into the system prompt for that turn only. This gives the
model a breadcrumb of what was discussed without consuming the full token cost.

```python
from hestia.config import HestiaConfig, CompressionConfig

config = HestiaConfig(
    ...,
    compression=CompressionConfig(enabled=True, max_chars=400),
)
```

### Session handoff summaries

When enabled, Hestia generates a 2-3 sentence summary when a session closes and
stores it as a memory entry tagged `handoff`. The next time you talk to Hestia,
this summary is available to the model via the normal memory search tools.

```python
from hestia.config import HestiaConfig, HandoffConfig

config = HestiaConfig(
    ...,
    handoff=HandoffConfig(enabled=True, min_messages=4, max_chars=350),
)
```

Both features are disabled by default. `TrustConfig.household()` and
`TrustConfig.developer()` imply `enabled=True` for both.

### What happens when the protected block exceeds budget

If your identity, memory epoch, and system prompt together are larger than the
per-slot budget, Hestia raises a visible warning instead of silently truncating:

```
⚠️ This session has grown past my context budget (8,192 tokens per slot).
I've saved a summary of our conversation. Type /reset to start fresh,
and I'll keep the summary for reference.
```

Options to fix it:
- Reduce `IdentityConfig.max_tokens` or shorten `SOUL.md`.
- Increase `--ctx-size / --parallel` (requires more VRAM).
- Run `/reset` to archive the session and start fresh.

---

## Configuration

Config is a Python file that defines a `config` variable of type `HestiaConfig`. Python (not YAML, not TOML) because you get IDE autocompletion, type checking, and the ability to compute values at load time.

```python
from pathlib import Path
from hestia.config import (
    HestiaConfig, InferenceConfig, SlotConfig,
    SchedulerConfig, StorageConfig, TelegramConfig,
)

config = HestiaConfig(
    inference=InferenceConfig(
        base_url="http://localhost:8001",
        model_name="your-model-Q4_K_M.gguf",  # Must match your GGUF filename
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

| Section | What it controls |
|---------|-----------------|
| `InferenceConfig` | Where your llama.cpp server lives, which model to use, token budgets |
| `SlotConfig` | KV-cache slot directory and pool size (match your `-np` flag) |
| `SchedulerConfig` | How often to check for due tasks (default: every 5 seconds) |
| `StorageConfig` | Database URL, where artifacts go, which directories file tools can access |
| `TelegramConfig` | Bot token, who's allowed to talk to it, rate limiting |

CLI flags (`--config`, `--db-path`, `--inference-url`, `--verbose`) override config values.

**PostgreSQL.** SQLite is the default and requires no extra dependencies. For PostgreSQL, install the `postgres` extra:

```bash
uv sync --extra postgres
# or
pip install hestia[postgres]
```

---

## Built-in tools

| Tool | What it does | Needs confirmation? |
|------|-------------|-------------------|
| `current_time` | Returns the current date and time | No |
| `read_file` | Reads a text file (sandboxed to `allowed_roots`) | No |
| `write_file` | Writes content to a file (sandboxed) | **Yes** |
| `list_dir` | Lists directory contents (sandboxed) | No |
| `terminal` | Executes a shell command | **Yes** |
| `http_get` | Fetches a URL (blocks private/internal IPs) | No |
| `read_artifact` | Retrieves the full content of an artifact by handle | No |
| `search_memory` | Searches long-term memory by keyword | No |
| `save_memory` | Saves a note to long-term memory | No |
| `list_memories` | Lists recent memories | No |
| `delegate_task` | Spawns a subagent with its own context | No |
| `email_list` | List emails in an IMAP folder | No |
| `email_read` | Read a single email by UID | No |
| `email_search` | Search emails (FROM/SUBJECT/SINCE) | No |
| `email_draft` | Create a draft in the Drafts folder | No |
| `email_send` | Send a previously created draft | **Yes** |
| `email_move` | Move a message to another folder | No |
| `email_flag` | Mark read/unread/starred | No |

Tools marked **Yes** require you to approve before they run. In headless mode (scheduler, daemon), these tools are denied by default — they fail closed, not open. You can change this with a trust profile (see [Trust profiles](#trust-profiles)).

### Email

Hestia can read your email via IMAP and draft (but not auto-send) replies via
SMTP. Send requires explicit confirmation. See the [email setup guide](docs/guides/email-setup.md) for walkthroughs for Gmail and Fastmail.

```python
from hestia.config import HestiaConfig, EmailConfig
from .email.secrets import IMAP_HOST, SMTP_HOST, USERNAME, PASSWORD

config = HestiaConfig(
    email=EmailConfig(
        imap_host=IMAP_HOST,
        smtp_host=SMTP_HOST,
        username=USERNAME,
        password=PASSWORD,
    ),
)
```

### Web search

Hestia ships a `web_search` tool that activates when you configure a provider
in your `config.py`:

```python
from hestia.config import HestiaConfig, WebSearchConfig
config = HestiaConfig(
    ...,
    web_search=WebSearchConfig(
        provider="tavily",
        api_key="tvly-...",   # https://tavily.com/ — free tier is 1000/month
        max_results=5,
    ),
)
```

Tavily is the only built-in provider today. Without a configured provider,
the tool simply isn't registered — the model won't see it in its tool list.
Combined with `http_get`, this gives Hestia search-then-fetch capability for
daily research and news tasks.

### Writing your own tools

```python
from hestia.tools.metadata import tool

@tool(
    name="weather",
    public_description="Get weather for a location",
    capabilities=["network_egress"],
)
async def get_weather(location: str) -> str:
    # your implementation
    return f"Weather for {location}: sunny, 22C"
```

Register it in your config or CLI setup and it's available to the model.

---

## Security

For the full security policy and responsible-disclosure process, see [`SECURITY.md`](SECURITY.md).

**Path sandboxing.** File tools (`read_file`, `write_file`, `list_dir`) can only access directories listed in `storage.allowed_roots`. Attempts to read `/etc/shadow` or write to `~/.ssh` are rejected before the tool runs.

**SSRF protection.** `http_get` blocks requests to private IP ranges (localhost, 10.x, 172.16.x, 192.168.x, 169.254.x) to prevent the model from probing internal services or cloud metadata endpoints.

**Capability labels.** Every tool declares what it can do: `read_local`, `write_local`, `shell_exec`, `network_egress`, `memory_read`, `memory_write`, `orchestration`. The policy engine uses these to restrict access by context — subagents can't execute shell commands, scheduled tasks can't write files.

**Confirmation enforcement.** Dangerous tools require explicit user approval. If no confirmation mechanism is available (headless mode), the tool is denied unless the active trust profile auto-approves it. This is enforced on both the direct path and the meta-tool path.

**Prompt-injection detection.** Tool results are scanned for known injection patterns and anomalous entropy before they enter the model context. Hits are annotated (never blocked) so the model treats the content as untrusted. Configurable via `SecurityConfig`.

**Egress auditing.** Every outbound HTTP request from `http_get` and `web_search` is logged to the trace store. Use `hestia audit egress --since=7d` to review domain-level aggregates and spot anomalies.

**User allowlists.** Telegram and Matrix adapters support allowlists. Only authorized users or rooms can interact with the bot.

**Config file execution.** Hestia config files are Python modules loaded via `importlib`. This means a config file can execute arbitrary code — this is intentional (it lets you compute config values, import secrets from environment variables, etc.), but you should treat config files with the same caution as any executable script. Never load a config file from an untrusted source.

---

## Running on your hardware

Hestia is built for consumer GPUs. Here's what to expect:

### Recommended models

| Model | Parameters | Quantization | VRAM | Strengths | Notes |
|-------|-----------|--------------|------|-----------|-------|
| Llama-3.1-8B-Instruct | 8B | Q4_K_M | ~6GB | Tool calling, general | Default recommendation |
| Qwen 2.5 7B Instruct | 7B | Q4_K_M | ~5GB | Tool calling, structured output | Solid alternative |
| Llama-3.2-3B-Instruct | 3B | Q5_K_M | ~3GB | Speed | Light identity-check workload |
| Qwen 2.5 14B Instruct | 14B | Q4_K_M | ~10GB | Quality | Needs ≥12GB VRAM |

Static K-quants (Q4_K_M, Q6_K_M) work well; avoid imatrix (I-) quants, which can corrupt tool-calling. The same project-wide guidance from `~/AGENTS.md` applies.

| VRAM | Model | Slots | Context | Experience |
|------|-------|-------|---------|-----------|
| 8 GB | 3-4B Q4 | 2 | 8K | Works, but tool chaining is limited |
| 12 GB | 7-9B Q4 | 4 | 16K | The sweet spot — Qwen 3.5 9B recommended |
| 16 GB | 9-12B Q4/Q6 | 4 | 16-24K | Comfortable. Room for longer conversations |
| 24 GB | 12-14B Q6/Q8 | 4-6 | 32K | Multi-session without eviction pressure |

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

The flags that matter: `-np 4` sets 4 KV-cache slots (match `SlotConfig.pool_size`). `--cache-type-k turbo3` and `--cache-type-v turbo3` quantize the KV-cache to ~3 bits per value (more compact than the older `q4_0`), which roughly doubles the context you can fit in the same VRAM on RTX 30/40-series GPUs. `--slot-save-path` enables save/restore so Hestia can checkpoint and resume sessions from disk.

### What makes Hestia efficient

- **Real token counting** via llama.cpp's `/tokenize` — no estimates, no surprises
- **Meta-tool pattern** — two generic tools instead of describing all 11 individually (~2,900 tokens saved per request)
- **KV-cache save/restore** — resuming a warm session skips prompt re-ingestion entirely (~200ms from NVMe)
- **Automatic artifact overflow** — large tool results go to disk, only a preview enters context
- **Truncation-first compression** — drops oldest messages at build time, no summarization in the hot path

---

## Running Hestia as a daemon

The `deploy/` directory contains systemd service templates for persistent operation:

| File | Purpose |
|------|---------|
| `hestia-llama.service` | llama.cpp inference server with KV-cache slots (port 8001) |
| `hestia-agent.service` | Hestia agent (Telegram bot + scheduler daemon) |
| `hestia-llama.alt-port.service.example` | Alternate llama.cpp server on port 8002 (rename to `.service` to use) |
| `install.sh` | Copies services to `/etc/systemd/system/` and reloads daemon |
| `example_config.py` | Configuration template — copy and customize |

Quick start (system-wide):

```bash
sudo deploy/install.sh $USER
sudo systemctl enable --now hestia-llama@$USER
sudo systemctl enable --now hestia-agent@$USER
```

`hestia-agent` depends on `hestia-llama` — systemd starts them in the right order and restarts on failure.

For a per-user systemd setup:

```bash
systemctl --user daemon-reload
systemctl --user enable --now hestia-llama@$USER
systemctl --user enable --now hestia-agent@$USER
```

Configure secrets via environment variables so they never live in source control:

```bash
export HESTIA_SOUL_PATH=/opt/hestia/SOUL.md
export HESTIA_CALIBRATION_PATH=/opt/hestia/docs/calibration.json
export HESTIA_EXPERIMENTAL_SKILLS=1
export EMAIL_APP_PASSWORD="your-app-password"
```

Reference them in `config.py`:

```python
from hestia.config import HestiaConfig, EmailConfig

config = HestiaConfig(
    email=EmailConfig(
        password_env="EMAIL_APP_PASSWORD",
    ),
)
```

See [`deploy/README.md`](deploy/README.md) for the full operator walkthrough.

---

## CLI reference

```
hestia [OPTIONS] COMMAND

Options:
  --config PATH          Python config file
  --db-path PATH         Override database location
  --inference-url TEXT   llama.cpp server URL
  --model TEXT           Model filename
  -v, --verbose          DEBUG logging

Commands:
  chat                   Interactive conversation
  ask MESSAGE            Single message, single response
  init                   Set up database, artifacts, slots
  health                 Check llama.cpp server status

  telegram               Run as Telegram bot
  matrix                 Run as Matrix bot

  status                 System overview
  version                Version info

  memory search QUERY    Search long-term memory
  memory list            Recent memories
  memory add TEXT        Save a memory
  memory remove ID       Delete a memory

  failures list          Recent failure records
  failures summary       Failure counts by class

  schedule add           Create a cron or one-shot task
  schedule list          List tasks
  schedule run ID        Trigger a task manually
  schedule enable ID     Enable a task
  schedule disable ID    Disable a task
  schedule remove ID     Remove a task
  schedule daemon        Run the scheduler loop
```

---

## Development

```bash
uv sync                                          # install deps
uv run pytest tests/unit/ tests/integration/ -q  # tests
uv run ruff check src/ tests/                    # lint
uv run ruff format src/ tests/                   # format
uv run mypy src/hestia                           # type check
```

### Branch model

- `main` — tagged releases only
- `develop` — integration branch
- `feature/<slug>` — one branch per task
- `release/<version>` — stabilization before tagging
- `hotfix/<slug>` — urgent fixes off main

### Architecture decisions

20+ ADRs in [`docs/DECISIONS.md`](docs/DECISIONS.md) covering everything from why it's called Hestia to why FTS5 over vector search.

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
