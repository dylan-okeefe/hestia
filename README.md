# Hestia

A local-first personal assistant framework for people running their own LLMs on constrained consumer hardware (8–16 GB VRAM, one GPU).

Hestia is designed for self-hosters who want a capable AI assistant without sending their conversations to the cloud. It's opinionated, lightweight, and built specifically for llama.cpp. No LangChain. No transformers. No vector DB required.

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

## Status

**Pre-alpha.** This project is under active development and not yet ready for general use. APIs will change. Features are incomplete. Use at your own risk.

## Branch Model

- `main` — Released, tagged versions only. Never committed to directly.
- `develop` — Integration branch. Features merge here.
- `feature/<slug>` — One per task.
- `release/<version>` — Stabilization before a tag.
- `hotfix/<slug>` — Urgent fix off `main`.

## License

Apache 2.0 — see [LICENSE](LICENSE).
