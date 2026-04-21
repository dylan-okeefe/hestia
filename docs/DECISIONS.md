# Architectural Decision Records

This index points to every ADR in the project. Each ADR lives as a separate
file in [`docs/adr/`](adr/) so it can be linked, versioned, and updated
independently.

| ADR | Title | Status |
|-----|-------|--------|
| ADR-0001 | [Project name is "Hestia"](adr/ADR-0001-project-name-is-hestia.md) | Accepted |
| ADR-0002 | [Package manager is `uv`](adr/ADR-0002-package-manager-is-uv.md) | Accepted |
| ADR-0003 | [Language is Python 3.11+](adr/ADR-0003-language-is-python-311.md) | Accepted |
| ADR-0004 | [Persistence is SQLAlchemy Core async with SQLite default, Postgres via URL override](adr/ADR-0004-persistence-is-sqlalchemy-core-async-with-sqlite-default-postgres-via-url-override.md) | Accepted |
| ADR-0005 | [Subagents run in the same process](adr/ADR-0005-subagents-run-in-the-same-process.md) | Accepted |
| ADR-0006 | [Search is FTS-only at first](adr/ADR-0006-search-is-fts-only-at-first.md) | Accepted |
| ADR-0007 | [No web UI in v1](adr/ADR-0007-no-web-ui-in-v1.md) | Accepted |
| ADR-0008 | [License is Apache 2.0](adr/ADR-0008-license-is-apache-20.md) | Accepted |
| ADR-0009 | [count_request correction factor measured but high variance [SUPERSEDED]](adr/ADR-0009-count_request-correction-factor-measured-but-high-variance-superseded.md) | Superseded by ADR-0011 |
| ADR-0010 | [Handoff docs live in `docs/handoffs/` inside the repo](adr/ADR-0010-handoff-docs-live-in-docshandoffs-inside-the-repo.md) | Accepted |
| ADR-0011 | [Calibration is two numbers (body factor + meta-tool overhead)](adr/ADR-0011-calibration-is-two-numbers-body-factor-meta-tool-overhead.md) | Accepted |
| ADR-0012 | [Turn state machine with platform-agnostic confirmation callback](adr/ADR-0012-turn-state-machine-with-platform-agnostic-confirmation-callback.md) | Accepted |
| ADR-0013 | [SlotManager owns KV-cache slot lifecycle with LRU eviction](adr/ADR-0013-slotmanager-owns-kv-cache-slot-lifecycle-with-lru-eviction.md) | Accepted |
| ADR-0014 | [Context resilience — compression, handoff summaries, and overflow signals](adr/ADR-0014-context-resilience.md) | Accepted |
| ADR-0015 | [llama-server coexistence modes](adr/ADR-0015-llama-server-coexistence.md) | Accepted |
| ADR-0016 | [Telegram adapter forces HTTP/1.1, rate-limits edits, and whitelists users](adr/ADR-0016-telegram-adapter-forces-http11-rate-limits-edits-and-whitelists-users.md) | Accepted |
| ADR-0017 | [Prompt-injection detection and network egress auditing](adr/ADR-0017-prompt-injection-detection-and-egress-audit.md) | Accepted |
| ADR-0018 | [Reflection loop architecture](adr/ADR-0018-reflection-loop-architecture.md) | Accepted |
| ADR-0019 | [Style profile vs. identity separation](adr/ADR-0019-style-profile-vs-identity.md) | Accepted |
| ADR-0020 | [CLI decomposition into `app.py` + `platforms/runners.py`](adr/ADR-0020-cli-decomposition.md) | Accepted — implemented in v0.7.4 (loop L30). |
| ADR-0021 | [ContextBuilder Prefix Registry and Tokenize Cache](adr/ADR-0021-context-builder-prefix-registry-and-tokenize-cache.md) | Accepted (registry in v0.7.7, cache in v0.7.8) |
| ADR-0022 | [Skills Preview Feature Flag](adr/ADR-0022-skills-preview-feature-flag.md) | Accepted (v0.7.11) |
| ADR-0023 | [Memory Epochs — Compiled Prompt-Facing Views](adr/ADR-0023-memory-epochs.md) | Accepted |
| ADR-0024 | [Skills as User-Defined Python Functions](adr/ADR-0024-skills-user-defined-python-functions.md) | Accepted |
| ADR-0025 | [Identity as a Compiled, Bounded, Operator-Owned Document](adr/ADR-0025-identity-compiled-bounded-operator-owned.md) | Accepted |
| ADR-0026 | [Discord Always-Listening Voice Channel](adr/ADR-0026-discord-voice-architecture.md) | Unknown |
| ADR-0027 | [Scheduler runs scheduled tasks via the existing Orchestrator](adr/ADR-0027-scheduler-runs-scheduled-tasks-via-the-existing-orchestrator.md) | Accepted |
| ADR-0028 | [HestiaConfig is a typed Python dataclass loaded from a Python file](adr/ADR-0028-hestiaconfig-is-a-typed-python-dataclass-loaded-from-a-python-file.md) | Accepted |
| ADR-0029 | [Long-term memory uses SQLite FTS5, not vector search](adr/ADR-0029-long-term-memory-uses-sqlite-fts5-not-vector-search.md) | Accepted |
| ADR-0030 | [Subagent delegation uses same-process, different-slot architecture](adr/ADR-0030-subagent-delegation-uses-same-process-different-slot-architecture.md) | Accepted |
| ADR-0031 | [Capability labels and session-aware tool filtering](adr/ADR-0031-capability-labels-and-session-aware-tool-filtering.md) | Accepted |
| ADR-0032 | [Typed failure bundles](adr/ADR-0032-typed-failure-bundles.md) | Accepted |
| ADR-0033 | [Matrix adapter with room-based session mapping and allowlist](adr/ADR-0033-matrix-adapter-with-room-based-session-mapping-and-allowlist.md) | Accepted |

---

> **Historical note:** ADRs 0001–0013, 0016, and 0027–0033 were migrated
> from the legacy inline `DECISIONS.md` format during loop L47.
> Some ADR numbers were changed to resolve collisions with existing
> separate-file ADRs. See `docs/handoffs/L47-adr-normalization-handoff.md`
> for the full mapping.

