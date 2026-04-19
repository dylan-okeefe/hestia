# Kimi loop L23 — Telegram + Matrix confirmation callbacks

## Review carry-forward

From **L22 review** (merged to `develop` in commit `75ea2b5`):

1. **Mypy is now at 0 with strict on `hestia.policy.*` and `hestia.core.*`.**
   New code in L23 must not regress this. Adapter-level code in
   `hestia.platforms.*` is **not yet** strict, but don't add `Any`-typed
   callbacks unless there's a clear reason. Prefer `Awaitable[bool]`,
   `Callable[[str], Awaitable[None]]`, etc., matching the patterns
   already in `orchestrator/engine.py`.
2. **`SchedulerStore` None-handling pattern** (L22 §3, commit `85d7fd6`)
   — when L23 adds per-confirmation storage, don't silently fall back
   if a store isn't configured; raise or log-and-fail, matching the
   `_require_scheduler_store` pattern. This keeps debug output honest
   when operators misconfigure a bot.
3. **ADR numbering** — L21 shipped ADR-0014 (context resilience) and
   ADR-0015 (llama-server coexistence). This spec mentioned
   "ADR-0015 platform-confirmation-callbacks" — **renumber to
   ADR-0016** before writing.
4. **No new ruff debt** — cli.py has 9 pre-existing ruff errors
   (SIM108, unused `db`). If L23 touches those files and ruff
   complains, include the fix in a separate `style:` commit, same as
   L21. Don't leave partial cleanup.
5. **L21 handoff summarizer routing** — when the Telegram / Matrix
   confirmation flow has to abort a turn (timeout or ❌), route the
   session teardown through `Orchestrator.close_session` if the
   session is being closed, not `SessionStore.archive_session` —
   otherwise the L21 handoff summary is silently skipped.

**Branch:** `feature/l23-platform-confirmation` from **`develop`**.

---

## Goal

L20 introduced `TrustConfig.auto_approve_tools` for operators who want
headless convenience. Operators who **want** a confirmation prompt on their
phone — the audit's Option A — still can't get one. This loop wires real
confirmation callbacks into Telegram and Matrix so `requires_confirmation=True`
tools (`terminal`, `write_file`, `email_send`) work end-to-end on mobile.

Source: [`reviews/capability-audit-april-17.md`](../reviews/capability-audit-april-17.md)
§1 Option A (cli.py:1146-1148 and cli.py:1276-1278 TODOs).

Target version: **0.5.0** (minor — new inter-platform behavior).

---

## Scope

### §1 — Telegram inline-keyboard confirmation

- `cli.py:1146-1148` TODO: build a confirmation callback that uses
  python-telegram-bot's `InlineKeyboardMarkup` with ✅ / ❌ buttons.
- Implementation lives in `src/hestia/platforms/telegram_adapter.py`.
- Per-call state held in a small in-memory dict keyed on the generated
  callback ID; GC entries after 60 s timeout.
- Tool args rendered as a short JSON snippet in the prompt (truncate long
  fields to ~200 chars each).
- Callback returns `True` on ✅, `False` on ❌ or timeout.

### §2 — Matrix reply-pattern confirmation

- `cli.py:1276-1278` TODO: on confirmation, post a message
  `Tool '{name}' wants to run with: {args}. Reply 'yes' or 'no' within 60 s.`
- Adapter hooks `matrix-nio`'s RoomMessage event handler for 60 s matching
  on the reply's `in_reply_to` event id.
- Trailing timeout → `False`.

### §3 — Shared infrastructure

- Factor the "render args for human review" helper into
  `src/hestia/platforms/confirmation.py` so both adapters share it.
- Add `ConfirmationRequest` dataclass: `id, tool_name, arguments, prompt,
  created_at, expires_at`.
- Add `ConfirmationStore` (in-memory for now, with a clear upgrade path to
  persistent) to correlate responses with requests.

### §4 — TrustConfig interaction

- Operator can still list `auto_approve_tools` in TrustConfig; the orchestrator
  skips the confirm callback for those. Documented.
- New TrustConfig preset method `TrustConfig.prompt_on_mobile()` that sets
  `auto_approve_tools=[]` but leaves the other flags at household defaults.

### §5 — Tests & docs

- Unit: mocked python-telegram-bot + matrix-nio clients, verify both paths.
- Integration: end-to-end Matrix confirmation against the mock homeserver in
  `tests/integration/test_memory_matrix_mock.py`.
- README: update trust profiles section with the new confirmation flow.
- ADR-0016 `platform-confirmation-callbacks.md` documenting the decision
  (ADR-0014 and ADR-0015 were taken by L21).

---

## Acceptance criteria

1. From Telegram, issuing a command that triggers `write_file` produces an
   inline-keyboard prompt and the tool runs only on ✅.
2. From Matrix, the same flow works with a reply-with-text pattern.
3. Timeout (60 s default, configurable) behaves as `False` (denied).
4. `TrustConfig.auto_approve_tools` still bypasses the prompt.
5. All new code passes mypy at strict.

## Post-loop self-check

- [ ] Test counts green.
- [ ] Mypy / Ruff counts not regressed.
- [ ] `CHANGELOG.md`, `pyproject.toml`, `uv.lock` bumped to 0.5.0.
- [ ] Handoff report written.
