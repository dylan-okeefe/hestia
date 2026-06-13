# Hestia

A local-first personal AI assistant that runs on your own hardware. Hestia connects
to your chat platforms, manages scheduled tasks, executes workflows, operates a
real browser for authenticated sites, and provides a full web dashboard for
administration — all without sending your data to third-party AI services.

Built for Ubuntu + NVIDIA RTX-class GPUs with [llama.cpp](https://github.com/ggerganov/llama.cpp)
as the inference backend.

## Features

### Chat Platforms
- **Telegram** — text, voice messages (STT/TTS), inline-keyboard confirmations
- **Matrix** — room-based sessions, reply-pattern confirmations
- **Email** — IMAP read/search/draft + SMTP send with HTML sanitization
- **CLI** — interactive terminal chat with session history

### Local Inference
- llama.cpp backend with KV-cache slot management (HOT/WARM/COLD temperature states)
- Streaming inference with progressive delivery to Telegram
- Token-budget-aware context building with per-message caching
- Configurable model, context length, and reasoning budget

### [Web Dashboard](docs/guides/web-dashboard.md) (React + FastAPI)
- **14-page admin SPA** — Dashboard, Sessions, Proposals, Style Profile, Scheduler,
  Security & Health, Config, Workflows, Profile, Knowledge, Error Log, Admin Users
- **Authentication** — platform-based 2FA (code via Telegram/Matrix), token sessions,
  role-based access control (admin / user)
- **Responsive design** — mobile sidebar, desktop persistent nav, dark mode

### [Workflows](docs/guides/workflows.md)
- **Visual workflow editor** — React Flow canvas with drag-and-drop nodes and edges
- **Triggers** — manual, schedule (cron), chat command, webhook, email, message,
  proposal, tool error, workflow completed, session started
- **Node types** — Tool Call, LLM Decision, Send Message, HTTP Request, Condition,
  Investigate, Inference
- **Versioning** — save multiple versions, activate specific versions, test runs
- **Variable interpolation** — `{{data.field}}` syntax with frontend auto-insertion

### [Browser Sessions](docs/guides/browser-sessions.md)
- **Persistent browser automation** — cookies and localStorage per-domain via Playwright
- **Headless streaming** — interact with sites via CDP screencast in the web UI
- **Headed fallback** — real browser window for bot-blocking sites (Indeed, LinkedIn)
- **Anti-detection** — playwright-stealth with WebGL spoofing, UA override, navigator masking
- **Session health checks** — verify stored sessions are still authenticated

### Memory & Context
- **Long-term memory** — SQLite FTS5 full-text search with BM25 ranking
- **Memory epochs** — 30-day rolling summaries injected into context
- **Per-user memory scoping** — isolated memory per identity, fail-closed when identity
  is missing
- **Handoff summaries** — automatic session-close summaries for conversation continuity

### Background Systems
- **Scheduler** — cron-based recurring tasks with web UI management
- **Reflection loop** — three-pass pattern mining → proposal generation → queue write
- **Style profile** — per-user interaction-style learning (length, formality, topics,
  activity window)
- **Proposals** — agent-generated improvement suggestions with accept/reject/defer lifecycle

### [Security](docs/guides/security.md)
- **Trust presets** — paranoid, household, developer, prompt_on_mobile; gate destructive
  tools per context
- **Prompt-injection scanner** — regex + entropy heuristics with structured-content bypass
- **Egress audit** — logs every outbound HTTP request with anomaly detection
- **SSRF protection** — URL validation with IPv4-mapped-IPv6 normalization and CGNAT blocking
- **Path sandboxing** — `allowed_roots` restricts file tool access
- **Webhook HMAC verification** — per-workflow secrets with replay-attack protection

### Tools (35+ built-ins)

Filesystem: `read_file`, `write_file`, `edit_file`, `append_to_file`, `list_dir`, `glob`, `grep`  
Shell: `terminal`  
Web: `http_get`, `web_search`, `search_web`, `browser_get`, `browser_login`  
Email: `email_list`, `email_read`, `email_search`, `email_search_and_read`, `email_draft`, `email_send`, `email_move`, `email_flag`  
Memory: `save_memory`, `search_memory`, `list_memories`, `delete_memory`  
Scheduler: `create_scheduled_task`, `list_scheduled_tasks`, `disable_scheduled_task`, `enable_scheduled_task`, `delete_scheduled_task`  
Proposals: `list_proposals`, `show_proposal`, `accept_proposal`, `reject_proposal`, `defer_proposal`  
Style: `show_style_profile`, `reset_style_metric`, `reset_style_profile`  
Workflow: `save_job_alert`, `list_pending_alerts`, `mark_alerts_sent`  
System: `current_time`, `read_artifact`, `rollback_turn`, `delegate_task`

## Quick Start

```bash
git clone <repo-url>
cd hestia
uv sync
cp deploy/example_config.py config.py
# Edit config.py: set inference.model_name, telegram.bot_token, etc.
hestia init
# Start the llama.cpp server (see deploy/hestia-llama.service or docs/guides/runtime-setup.md)
hestia serve
```

`hestia serve` runs all configured platform adapters and the web dashboard. Use
`hestia chat` for a local REPL. Note that `web.enabled` defaults to `False`; set it
to `True` in `config.py` to enable the dashboard.

Hestia bootstraps its database with `create_tables()` plus idempotent runtime
migrations on every startup. The Alembic files under `migrations/` exist for
reference and development convenience, but they are **not** the production
upgrade path. Running `hestia init` is sufficient.

## Documentation

- **[User Guides](docs/guides/)** — setup, platforms, security, voice, email, browser
  sessions, workflows, multi-user, custom tools
- **[Architecture Decisions](docs/adr/)** — 39 ADRs covering design rationale
- **[Changelog](CHANGELOG.md)** — version history
- **[Release Notes](docs/releases/)** — human-facing release summaries
- **[Security](SECURITY.md)** — threat model and responsible disclosure

## Architecture

```
src/hestia/
  cli.py              # CLI entry point
  config.py           # HestiaConfig typed dataclass
  core/               # Types, inference client, serialization
  context/            # ContextBuilder with prefix layers and tokenize cache
  orchestrator/       # Turn state machine, tool dispatch, streaming
  inference/          # SlotManager for llama.cpp KV-cache lifecycle
  scheduler/          # Background cron task loop
  tools/              # Tool registry + 20+ built-ins
  artifacts/          # Artifact storage
  persistence/        # Database layer (SQLite/PostgreSQL)
  platforms/          # Platform ABC + Telegram, Matrix, Email, CLI adapters
  policy/             # Policy engine with trust presets and capability labels
  web/                # FastAPI routes, auth middleware, static assets
  voice/              # STT/TTS pipeline (faster-whisper + Piper)
  email/              # IMAP/SMTP adapter
  reflection/         # Background analysis and proposal generation
  style/              # Per-user interaction-style learning
  security/           # Injection scanner, egress audit
```

## License

Apache-2.0
