# Kimi loop L23 — Telegram + Matrix confirmation callbacks

## Review carry-forward

From L22 review (to be filled when L22 merges).

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
- ADR-0015 `platform-confirmation-callbacks.md` documenting the decision.

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
