# L194 — Release Polish

**Status:** Spec ready  
**Branch:** `feature/l194-release-polish` (from `develop`)  
**Target release:** v0.12.0

## Intent

Nice-to-have improvements that improve first impressions and reduce support burden. Not release blockers, but worth doing while the release is being prepared.

---

## Scope

### §1 — Web dashboard quickstart guide

**Create `docs/guides/web-dashboard.md`:**

A 2-page overview covering:
- How to access the dashboard (`http://host:port`)
- Login flow (if auth is enabled)
- Dashboard pages and what they do:
  - **Dashboard** — overview, stats, recent activity
  - **Proposals** — review and approve/reject agent proposals
  - **Style** — manage style profiles
  - **Scheduler** — view and manage scheduled tasks
  - **Security & Health** — health checks and security status
  - **Config** — view configuration (read-only)
  - **Workflows** — list and edit workflows
  - **Profile** — user profile and knowledge
  - **Knowledge** — memory search and session history
  - **Errors** — error dashboard (admin only)
  - **Users** — user management (admin only)
- Dark mode toggle location
- Mobile usage notes

**Commit:** `docs: add web dashboard quickstart guide`

---

### §2 — Workflow basics guide

**Create `docs/guides/workflows.md`:**

Cover the workflow system for users:
- **What is a workflow** — trigger + nodes + edges
- **Triggers** — manual, schedule (cron), chat command, webhook, message, email, proposal, tool error, workflow completed, session started
- **Nodes** — Tool Call, LLM Decision, Send Message, HTTP Request, Condition, Investigate, Inference
- **Variables** — `{{data.command}}` syntax, where values come from
- **Building a workflow** — open editor, add nodes, connect edges, configure triggers
- **Test runs** — run a workflow manually to verify behavior
- **Execution history** — view past runs and their results

**Commit:** `docs: add workflow basics guide`

---

### §3 — Rewrite root README.md

**In `README.md` (repo root):**

Current state: identical copy of `docs/README.md` (a docs index). Replace with a proper project overview:

```markdown
# Hestia

A personal AI assistant that runs locally. Hestia connects to your chat platforms (Telegram, Matrix), manages scheduled tasks, executes workflows, and provides a web dashboard for administration.

## Features

- **Local inference** — runs on your own hardware via llama.cpp
- **Multi-platform** — Telegram, Matrix, CLI, Discord (voice)
- **Workflows** — visual workflow editor with triggers and nodes
- **Web dashboard** — admin UI with auth, dark mode, responsive design
- **User registry** — multi-user support with roles and trust levels
- **Memory** — long-term searchable memory with FTS5
- **Scheduler** — cron-based recurring tasks
- **Trust system** — paranoid to developer presets for tool approval

## Quick Start

```bash
pip install hestia
hestia --config config.py serve
```

See [docs/guides/runtime-setup.md](docs/guides/runtime-setup.md) for detailed setup.

## Documentation

- [User Guides](docs/guides/) — setup, platforms, security, voice
- [Architecture Decisions](docs/adr/) — design rationale
- [Changelog](CHANGELOG.md) — version history

## License

MIT
```

Keep it concise. Link to docs for details.

**Commit:** `docs: rewrite root README as project overview`

---

### §4 — Document webhook endpoint uniqueness limitation (P0-4)

**Why:** If multiple workflows share the same webhook endpoint, a valid signature from any of their secrets authenticates the request, and the event broadcasts to all matching workflows.

**Add a note in `docs/guides/workflows.md` (from §2) or create a small security note:**

> **Webhook Security Note:** Each workflow generates a unique webhook secret. If two workflows are configured with the same webhook endpoint URL, a valid request signed with either secret will be accepted and broadcast to both workflows. Keep endpoint URLs unique per workflow.

**Commit:** `docs: document webhook endpoint uniqueness limitation`

---

## Quality gates

- All new markdown files render correctly
- Root README.md is a proper project overview, not a docs index
- No broken internal links

## Handoff

- Verify a new reader can understand what Hestia is from the root README alone
- Verify the web dashboard guide covers all 11 pages
- Verify the workflow guide explains triggers, nodes, and variables clearly
