# L222 — Trust/capability boundary handoff

**Branch:** `feature/l222-trust-capability-boundary`  
**Parent:** `feature/l221-session-concurrency`  
**Status:** Implementation complete, acceptance green.

## What changed

Implemented the unified trust/capability boundary spec from `docs/development-process/L222-trust-capability-boundary.md` and `docs/reviews/decisions-trust-capability-boundary.md`.

### §1 — `CapabilityGate` core
- Added `src/hestia/policy/gate.py`, `src/hestia/policy/channel.py`, and `src/hestia/policy/identity.py`.
- `CapabilityGate.check` resolves identity, trust preset/overrides, tool capabilities, channel risk, global deny-list, and injection escalation before returning a decision.
- Decisions include `allowed`, `auto_approved`, `requires_confirmation`, `reason`, and a stable `request_token` when escalation requires confirmation.
- Added `CapabilityEventStore` + schema migration to persist deny/escalation audit events (feeds L223 blocked-actions digest).

### §2 — Route every tool-execution path through the gate
- `src/hestia/orchestrator/execution.py`: `TurnExecution._run_capability_gate` runs before any tool dispatch; denials surface as `[CATEGORY: BLOCKED]` tool results; escalations store `request_token` on `TurnContext` and fall through to the confirmation callback.
- `src/hestia/workflows/executor.py`: tool-type workflow nodes now construct a `CapabilityRequest(channel=Channel.WORKFLOW, ...)` and consult the gate with `workflow.allow_listed_tools`.
- `src/hestia/orchestrator/engine.py`: `process_turn` accepts and forwards `channel` to `TurnContext`.
- `src/hestia/app.py`: constructs `CapabilityGate` after the `ToolRegistry` is ready.
- CLI, Telegram, Matrix, scheduler, and subagent paths already passed the correct `Channel` from earlier work; this loop verified and tightened the wiring.
- Added `tests/unit/orchestrator/test_execution_gate.py` and `tests/unit/workflows/test_executor_trust.py`.
- Updated `tests/unit/workflows/test_executor.py` for the new gate-based workflow trust behavior.

### §3 — Identity model for group/room sessions
- Human-sender identity is resolved through `UserStore` and used as the trust actor, not the room/chat id.
- Covered by existing platform runner tests and gate identity tests.

### §4 — Confirmation binding
- `ConfirmCallback` signature extended to `(tool_name, arguments, request_token)`.
- Telegram and Matrix confirmation callbacks forward the token to `adapter.request_confirmation`.
- Updated unit + integration confirmation tests for the new signature.

### §5 — Webhook secret redaction
- `src/hestia/web/routes/workflows.py` redacts `trigger_config.secret` for non-owner/non-admin callers.

### §6 — Admin route hardening
- Diagnostic/global routes (`doctor`, `audit`, `config`, `tools`) require admin.
- Caller-scoped routes (`traces`, `egress`, `memory`) scope by resolved identity with admin-sees-all.

### §7 — Browser SSRF protection
- Shared SSRF helper in `src/hestia/security/ssrf.py` blocks loopback, link-local, cloud-metadata, and RFC1918 ranges.
- Applied before browser `page.goto()` and in `http_get` fallback.
- Browser fetch returns `[CATEGORY: BLOCKED]` for disallowed targets.

### §8 — Tool-result category markers
- Gate/retry logic recognizes `[CATEGORY: ...]` markers on tool results.
- Workflow executor and orchestrator surface gate denials with the marker.

## Acceptance

```bash
uv run pytest tests/unit/ tests/integration/ -q
# 1933 passed, 6 skipped

uv run mypy src/hestia
# Success: no issues found in 203 source files

uv run ruff check src tests/
# 68 errors (all pre-existing; all files touched by this loop are clean)
```

## Spec/decision item accounting

| Item | Status |
|------|--------|
| §1 `CapabilityGate` core + audit | done |
| §2 Route tool execution paths through gate | done |
| §3 Identity model for group/room sessions | done |
| §4 Confirmation binding | done |
| §5 Webhook secret redaction | done |
| §6 Admin route hardening | done |
| §7 Browser SSRF protection | done |
| §8 Tool-result category markers | done |
| Decision #1 — unattended destructive tools hard-deny + allow-list | done |
| Decision #2 — subagent inherits operator trust, injection gating | done |
| Decision #3 — injection escalation on all channels | done |
| Decision #4 — trust matrix explicit | done |
| Decision #5 — `trust_overrides` precedence | done |
| Decision #6 — admin/caller-scoped route split | done |
| Decision #7 — confirmation bound to requester only | done |
| Decision #8 — gate audit emit | done |

## Notable fixes during final wiring

1. **Workflow executor gate integration** — a subagent had added the gate object but had not actually routed tool-node execution through it; `_run_node` now calls `capability_gate.check` for unknown node types and respects `workflow.allow_listed_tools`.
2. **Test drift** — existing workflow trust tests assumed the old node-capability check; they were updated to assert gate-denial messages and allow-list behavior.
3. **Gate decision alignment** — `test_unknown_actor_on_untrusted_channel_is_restricted` was updated to use a destructive tool (`terminal`), matching decision #4 that unattended channels gate the *destructive subset*, not all tools.
4. **Callback signature migration** — unit/integration confirmation tests and platform-runner tests were updated for the new `request_token` parameter.
5. **Import hygiene** — fixed import ordering in `src/hestia/app.py` and moved the module logger below imports in `src/hestia/policy/gate.py` to satisfy ruff.

## Known issues / notes

- `tests/smoke/` includes environment-dependent tests requiring a live inference server; they were not part of the acceptance gate.
- The 68 remaining `ruff check src tests/` errors are pre-existing across the codebase and were not introduced by this loop.
- The branch should merge to `develop` only after L220/L221 land, per the release-prep sequence in the spec.
