# Architectural Decisions

This directory records architectural decisions made for Hestia.
Entries are append-only; when a decision is superseded, a new entry
references the old one rather than editing history.

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-001](adr/ADR-001-project-name-is-hestia.md) | Project name is "Hestia" | Accepted |
| [ADR-002](adr/ADR-002-package-manager-is-uv.md) | Package manager is `uv` | Accepted |
| [ADR-003](adr/ADR-003-language-is-python-3-11.md) | Language is Python 3.11+ | Accepted |
| [ADR-004](adr/ADR-004-persistence-is-sqlalchemy-core-async-with-sqlite-default-postgres-via-url-override.md) | Persistence is SQLAlchemy Core async with SQLite default, Postgres via URL override | Accepted |
| [ADR-005](adr/ADR-005-subagents-run-in-the-same-process.md) | Subagents run in the same process | Accepted |
| [ADR-006](adr/ADR-006-search-is-fts-only-at-first.md) | Search is FTS-only at first | Accepted |
| [ADR-007](adr/ADR-007-no-web-ui-in-v1.md) | No web UI in v1 | Accepted |
| [ADR-008](adr/ADR-008-license-is-apache-2-0.md) | License is Apache 2.0 | Accepted |
| [ADR-009](adr/ADR-009-count-request-correction-factor-measured-but-high-variance-superseded.md) | count_request correction factor measured but high variance [SUPERSEDED] | Superseded |
| [ADR-010](adr/ADR-010-handoff-docs-live-in-docs-handoffs-inside-the-repo.md) | Handoff docs live in `docs/handoffs/` inside the repo | Accepted |
| [ADR-011](adr/ADR-011-calibration-is-two-numbers-body-factor-meta-tool-overhead.md) | Calibration is two numbers (body factor + meta-tool overhead) | Accepted |
| [ADR-012](adr/ADR-012-turn-state-machine-with-platform-agnostic-confirmation-callback.md) | Turn state machine with platform-agnostic confirmation callback | Accepted |
| [ADR-013](adr/ADR-013-slotmanager-owns-kv-cache-slot-lifecycle-with-lru-eviction.md) | SlotManager owns KV-cache slot lifecycle with LRU eviction | Accepted |
| [ADR-014](adr/ADR-014-context-resilience.md) | Context resilience — compression, handoff summaries, and overflow signals | Accepted |
| [ADR-015](adr/ADR-015-llama-server-coexistence.md) | llama-server coexistence modes | Accepted |
| [ADR-016](adr/ADR-016-telegram-adapter-forces-http-1-1-rate-limits-edits-and-whitelists-users.md) | Telegram adapter forces HTTP/1.1, rate-limits edits, and whitelists users | Accepted |
| [ADR-017](adr/ADR-017-prompt-injection-detection-and-egress-audit.md) | Prompt-injection detection and network egress auditing | Accepted |
| [ADR-018](adr/ADR-018-reflection-loop-architecture.md) | Reflection loop architecture | Accepted |
| [ADR-019](adr/ADR-019-style-profile-vs-identity.md) | Style profile vs. identity separation | Accepted |
| [ADR-020](adr/ADR-020-cli-decomposition.md) | CLI decomposition into `app.py` + `platforms/runners.py` | Accepted |
| [ADR-021](adr/ADR-021-context-builder-prefix-registry-and-tokenize-cache.md) | ContextBuilder Prefix Registry and Tokenize Cache | Accepted |
| [ADR-022](adr/ADR-022-identity-compiled-bounded-operator-owned.md) | Identity as a Compiled, Bounded, Operator-Owned Document | Accepted |
| [ADR-023](adr/ADR-023-memory-epochs.md) | Memory Epochs — Compiled Prompt-Facing Views | Accepted |
| [ADR-024](adr/ADR-024-skills-user-defined-python-functions.md) | Skills as User-Defined Python Functions | Accepted |
| [ADR-025](adr/ADR-025-skills-preview-feature-flag.md) | Skills Preview Feature Flag | Accepted |
| [ADR-026](adr/ADR-026-discord-voice-architecture.md) | Discord Always-Listening Voice Channel | Abandoned |
| [ADR-027](adr/ADR-027-scheduler-runs-scheduled-tasks-via-the-existing-orchestrator.md) | Scheduler runs scheduled tasks via the existing Orchestrator | Accepted |
| [ADR-028](adr/ADR-028-hestiaconfig-is-a-typed-python-dataclass-loaded-from-a-python-file.md) | HestiaConfig is a typed Python dataclass loaded from a Python file | Accepted |
| [ADR-029](adr/ADR-029-long-term-memory-uses-sqlite-fts5-not-vector-search.md) | Long-term memory uses SQLite FTS5, not vector search | Accepted |
| [ADR-030](adr/ADR-030-subagent-delegation-uses-same-process-different-slot-architecture.md) | Subagent delegation uses same-process, different-slot architecture | Accepted |
| [ADR-031](adr/ADR-031-capability-labels-and-session-aware-tool-filtering.md) | Capability labels and session-aware tool filtering | Accepted |
| [ADR-032](adr/ADR-032-typed-failure-bundles.md) | Typed failure bundles | Accepted |
| [ADR-033](adr/ADR-033-matrix-adapter-with-room-based-session-mapping-and-allowlist.md) | Matrix adapter with room-based session mapping and allowlist | Accepted |

---

