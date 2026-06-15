# Triage Index — develop review 2026-06-12

> **Snapshot notice:** This index was written on 2026-06-12. Loop 1 (docs trio + accuracy pass) and several other items have since been completed on `develop`; the remaining `HOLD-FOR-REVIEW` security/concurrency/architecture items still require supervised design work. This document is retained as historical context.

This index maps every consolidated finding to a small, single-purpose loop.  It honors the review's intent: **one cycle on invariants and the front door, not more feature breadth.**  Findings that are facets of the same root problem are grouped into one coherent spec rather than fragmented.

Two root problems recur across many findings:
- **(a) Single enforced trust/capability boundary** — trust is currently split between `TrustConfig`, `policy/default.py`, the workflow executor's `_TRUST_CAPS`, and an unenforced `User.trust_preset`.
- **(b) Per-session concurrency model** — there is no per-session serialization; users, scheduler, and delegation can all race on the same session/slot/context.

## Legend

| Tag | Meaning |
|-----|---------|
| `SAFE-TO-AUTOMATE` | Contained, individually testable, low blast radius; implement tonight. |
| `HOLD-FOR-REVIEW` | Load-bearing security/concurrency/architecture change; produce spec + plan only, no production code until Dylan reviews. |

## Loop 1 — Docs trio + accuracy pass (SAFE-TO-AUTOMATE)

**Order: 1** (no dependencies)

**Findings covered**
- README Quick Start is wrong (`pip install hestia`, `--config config.py`, missing `uv`/`llama.cpp`/`init`, `web.enabled` defaults false).
- UPGRADE.md stops at v0.10.0 while project is past v0.12.x; documents non-existent `hestia skills` / `hestia memory epochs` commands and links missing guides.
- README tool names are wrong (`rollback` vs `rollback_turn`, `proposal_accept` vs `accept_proposal`, `scheduler_add` vs `create_scheduled_task`, `style_reset` vs `reset_style_profile`).
- SECURITY.md promises "responsible disclosure" but has no process, contact, or supported-versions.
- Three contradictory migration stories (`deploy/README.md` says Alembic, `persistence/migrations/__init__.py` says Hestia doesn't use Alembic, app bootstraps via `create_tables()` + runtime migrations).
- Architecture tree in README omits `workflows/`, `events/`, `memory/`, `tools/browser/`, `audit/`; design doc stale; `deploy/example_config.py` only covers Telegram+inference.
- Version numbers disagree across tag / CHANGELOG / `pyproject.toml` (`pyproject.toml` says 0.12.2, review says project is at 0.13.0).

**Scope**
1. Rewrite README Quick Start to the real path: clone → `uv sync` → copy `deploy/example_config.py` → `hestia init` → start `llama.cpp` server → `hestia serve` (or CLI/Telegram/etc.).
2. Bring UPGRADE.md current to the version in `pyproject.toml`/CHANGELOG, remove fictional commands and dead links.
3. Rewrite SECURITY.md with a disclosure process, contact, and supported-versions table.
4. Accuracy pass on README tool names against `list_tools` output / source registry.
5. Sync `pyproject.toml` version with CHANGELOG; add a one-line note in CHANGELOG if needed.
6. Add a short migration-truth paragraph to README/UPGRADE: Hestia uses bootstrap `create_tables()` + runtime migrations, not Alembic.

**Invariant / test**
- `tests/docs/test_readme.py` (or new `tests/docs/`) asserts Quick Start commands exist in code/docs examples and that every tool name mentioned in README matches a registered tool.
- `tests/docs/test_upgrade.py` asserts UPGRADE.md's top heading/version matches `pyproject.toml` and that no documented CLI command is unknown.
- `tests/docs/test_security.py` asserts SECURITY.md contains an email/contact string and a supported-versions section.
- `uv run pytest tests/docs` passes.

## Loop 2 — ruff E501/E402 cleanup (SAFE-TO-AUTOMATE)

**Order: 2** (no dependencies; do before any code loops so new changes start clean)

**Findings covered**
- 97 × E501 line-length violations.
- 18 × E402 import-position violations.
- `py.typed` marker missing despite docs implying typed-package status.

**Scope**
1. Run `ruff check --select E501,E402 --fix src/hestia tests` and review mechanically.
2. For lines that cannot be split cleanly, use parentheses or extract local variables.
3. Add `src/hestia/py.typed` marker file.
4. Do **not** chase other ruff rules; keep the diff limited to E501/E402.

**Invariant / test**
- `ruff check --select E501,E402 src/hestia tests` returns zero.
- `uv run pytest` still passes (no functional changes).

## Loop 3 — Trust/capability boundary unification (HOLD-FOR-REVIEW)

**Order: 5** (depends on Loop 2 lint baseline; **no code tonight**, spec only)  
**Spec:** `docs/reviews/spec-trust-capability-boundary.md`

**Findings covered**
- `config.runtime.py` wide-open trust is a deliberate developer setting; the real gap is that `User.trust_preset` is stored but ignored in `policy/default.py`.
- Workflow executor defines its own `_TRUST_CAPS` and bypasses the policy gate (`workflows/executor.py:549` calls `tool_registry.call` directly).
- Workflow tool nodes can therefore run `email_send`, `terminal`, `write_file` unattended.
- Per-user trust keyed on room/chat rather than sender (Matrix `sender_platform_user=None`, Telegram groups key on `chat.id`).
- Confirmation buttons not bound to requester in groups.
- Webhook secrets leak via `GET /api/workflows` (`workflows.py list_workflows` returns full `trigger_config`).
- Several diagnostic routes lack `require_admin`.

**Status**  
Spec written. No production code was changed for this loop. Implementation requires Dylan review/approval.

## Loop 4 — Per-session concurrency model (HOLD-FOR-REVIEW)

**Order: 6** (depends on Loop 2; **no code tonight**, spec only)  
**Spec:** `docs/reviews/spec-session-concurrency.md`

**Findings covered**
- No per-session turn serialization (`orchestrator/engine.py process_turn`, `platforms/runners.py on_message`, `scheduler/engine.py _fire_task`).
- Shared IMAP connection unsafe under concurrent async (`email/adapter.py` reuses ContextVar connection; `app.py:232` shares one `EmailAdapter`).
- Failed/partial turns leave stale slot KV cache (`orchestrator/finalization.py:103`).
- Stale in-memory session cache (`runners.py:153`).
- `finish_reason="tool_calls"` with zero valid tool calls burns iterations (`execution.py:183`).
- `correction=True` flag not persisted (missing messages column).
- Context window can emit invalid message sequences (`history_window_selector.py`).

**Status**  
Spec written. No production code was changed for this loop. Implementation requires Dylan review/approval.

## Loop 5 — Scheduler double-fire + retry-storm fix (SAFE-TO-AUTOMATE)

**Order: 3** (can land independently; safe because scheduler is already covered by tests)

**Findings covered**
- `_tick` lists due tasks and fires them, but `next_run_at` is not updated until `process_turn` returns, so the next 5s tick re-lists the same task.
- On error `next_run_at` is left in the past, so a broken cron retries every tick forever.

**Scope**
1. In `scheduler/engine.py _tick`, mark a task as "in-flight" (or update `next_run_at` to its computed next occurrence) **before** dispatching `process_turn`.
2. On failure, update `next_run_at` to `now + backoff` instead of leaving it in the past.
3. Cap retry backoff to avoid indefinite hammering.

**Invariant / test**
- New test: simulate two rapid `_tick` calls; the second call does not re-list a task already dispatched.
- New test: a task that raises updates `next_run_at` to a future time; the next `_tick` does not immediately re-fire it.
- Existing scheduler tests still pass.

## Loop 6 — Wire `reasoning_budget` and `max_tokens` into inference request (SAFE-TO-AUTOMATE)

**Order: 3** (independent)

**Findings covered**
- `InferenceClient.chat/chat_stream` accept `reasoning_budget` but never put it in the request body.
- `InferenceConfig.max_tokens` is never wired into the turn loop; it always uses the 1024 default.
- `turns.reasoning_budget` column is never written.

**Scope**
1. Add `reasoning_budget` and `max_tokens` to the llama.cpp/chat completion request body in `core/inference.py` for both streaming and non-streaming paths.
2. Persist `reasoning_budget` to the `turns` row when a turn starts.
3. Respect `InferenceConfig.max_tokens` in the turn loop if no per-turn override is provided.

**Invariant / test**
- New unit test patches the HTTP transport and asserts the request JSON contains `reasoning_budget` and `max_tokens`.
- New test asserts `turns.reasoning_budget` is written after `process_turn`.
- Existing inference tests pass.

## Loop 7 — WebSocket admin-check + localhost bind (SAFE-TO-AUTOMATE)

**Order: 4** (independent; small web change)

**Findings covered**
- `browser_stream_ws` only enforces admin role if `user_id is not None`; a valid OTP token without a registry mapping skips the gate.
- Web dashboard binds `0.0.0.0` (from review summary; likely `web/serve.py` or config default).

**Scope**
1. In `web/browser_sessions.py browser_stream_ws`, require admin role for **all** authenticated callers; treat missing `user_id` as unauthorized for the admin stream.
2. Change default web bind to `127.0.0.1`; keep `0.0.0.0` configurable via `host` setting.

**Invariant / test**
- New test: a request with valid OTP but no `user_id` mapping is rejected with 403.
- New test: admin role is required even when `user_id` is present.
- Web UI tests pass.

## Loop 8 — Web UI hygiene (SAFE-TO-AUTOMATE)

**Order: 4** (independent)

**Findings covered**
- Modal markup copy-pasted ~10 times; no `Modal.tsx`/`ConfirmDialog` component.
- Dashboard "Recent Sessions" actually shows workflow execution count (`Dashboard.tsx:121`).
- ContextLab is fully built but unreachable (no route).
- Dead components: `ProposalCard.tsx`, `FormField.tsx`, unused `t()` helper, unused API exports.

**Scope**
1. Extract `Modal.tsx` and `ConfirmDialog.tsx` from existing inline modal markup; replace the ~10 copies.
2. Fix Dashboard label: "Recent Sessions" → "Workflow Executions" (or show real recent sessions count).
3. Either add a route for `ContextLab` in `App.tsx` or delete the component and its nav entry.
4. Delete `ProposalCard.tsx`, `FormField.tsx`, and the unused `t()` helper if truly unused; verify with `npm run build`/`vitest`.
5. Keep inline `style={{}}` count under 20 per AGENTS.md.

**Invariant / test**
- `cd web-ui && grep -r "style={{" src/ | grep -v node_modules | wc -l` stays under 20.
- `npm run build` and `npm run test` (Vitest) pass.
- Playwright smoke tests pass if they exist.
- Dashboard label text matches the metric it displays.

## Loop 9 — Schema consolidation / `error_resolutions` bootstrap (SAFE-TO-AUTOMATE)

**Order: 3** (prerequisite for any persistence refactor, but this loop only fixes the immediate bootstrap gap)

**Findings covered**
- `error_resolutions` table exists only in Alembic, not in the `create_tables`/runtime-migration bootstrap path.
- `error_resolution_store.py` `list_statuses` IN-clause lacks `bindparam(expanding=True)`.
- Duplicate DDL / schema drift (`style_profiles`, `failure_bundles` declared in both `schema.py` and store `create_table()`; `proposals`/`memory` outside `schema.py`; `skills` only in Alembic).

**Scope for tonight (safe subset)**
1. Add `error_resolutions` table to the runtime bootstrap path (`persistence/schema.py` or equivalent `create_tables()`).
2. Fix `list_statuses` IN-clause to use `bindparam(expanding=True)`.
3. Do **not** refactor the full schema ownership model; that is architecture debt for a later cycle.

**Invariant / test**
- New test boots a fresh in-memory SQLite DB via the bootstrap path and asserts `error_resolutions` exists and `list_statuses([...])` works.
- Existing persistence tests pass.

## Loop 10 — `persistence/sessions.py` store split (HOLD-FOR-REVIEW)

**Order: 7** (depends on Loop 9 schema baseline; **no code tonight**, spec only)  
**Spec:** `docs/reviews/spec-persistence-store-split.md`

**Findings covered**
- `persistence/sessions.py` is 1044 lines / ~32 methods doing sessions + messages + turns + transitions + handoffs + slot fields + analytics.
- It imports `orchestrator.types`, creating an upward dependency from persistence to domain layer.

**Status**  
Spec written. No production code was changed for this loop. Implementation requires Dylan review/approval.

## Dependency order summary

```
1. Loop 1 — Docs trio + accuracy pass
2. Loop 2 — ruff E501/E402 cleanup
3. Loop 9 — error_resolutions bootstrap  (schema prerequisite)
4. Loop 5 — Scheduler double-fire fix
5. Loop 6 — reasoning_budget / max_tokens wiring
6. Loop 7 — WebSocket admin check + localhost bind
7. Loop 8 — Web UI hygiene
8. Loop 3 — Trust/capability boundary unification  (HOLD)
9. Loop 4 — Per-session concurrency model           (HOLD)
10. Loop 10 — persistence/sessions.py store split   (HOLD)
```

## What is intentionally out of scope for this cycle

- Browser SSRF protection (`browser_get`, `SessionStreamManager.start`) — requires deciding whether Playwright can ever touch loopback/cloud-metadata; leave for trust-boundary cycle.
- `email_inbound.py` marks-read-before-success — coupled to workflow finalization semantics; leave for concurrency/trust cycle.
- Tool-result summarization vs hard-truncate — product behavior decision.
- Full schema ownership refactor beyond `error_resolutions` bootstrap.
- `useWorkflowEditor.ts` decomposition, `api/client.ts` split, TanStack Query migration — valuable, but larger than one hygiene loop; schedule after invariant work.
- CLI/web duplicate validation layer — architecture decision.
- Telegram adapter modularization — code-quality-only, not invariant.
