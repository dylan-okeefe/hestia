# Matrix Integration — Design & Integration Test Plan

**Status:** `MatrixAdapter` + `hestia matrix` exist; this document remains the **design and test plan** reference. Update the status line when E2E harness is complete.

**Intent:** Matrix is the **automation-first** chat transport: scripted clients, CI-friendly end-to-end tests, and optional personal use alongside Telegram. ADR-007 positions Matrix as a v1 interface alongside CLI/Telegram; ADR-012 already assumes Matrix can supply `ConfirmCallback` patterns (reply buttons).

---

## 1. Goals and non-goals

### 1.1 Goals

- Implement `Platform` for Matrix so `Orchestrator.process_turn` is unchanged.
- Support **status updates** via `edit_message` (same UX pattern as Telegram).
- Map **stable session identity** to `SessionStore` (`platform="matrix"`, `platform_user=...`).
- Enable **headless integration tests** that send Matrix events and assert on bot replies without manual Telegram interaction.
- Keep secrets out of logs (access tokens, recovery keys).

### 1.2 Non-goals (v1 Matrix scope)

- Replacing Telegram as the primary operator UI (either can coexist).
- Full Element-feature parity (threads, polls, spaces).
- Multi-tenant or shared public bot rooms without an explicit allowlist.
- E2EE verification UX beyond what `matrix-nio` reasonably supports for a bot account.

---

## 2. Architecture

### 2.1 Placement in the codebase

```
src/hestia/platforms/
  base.py              # existing Platform ABC
  cli_adapter.py       # reference
  telegram_adapter.py  # reference
  matrix_adapter.py    # new: MatrixAdapter(Platform)
```

CLI entry point:

```text
hestia matrix   # analogous to hestia telegram
```

### 2.2 Dependencies

- **`matrix-nio`** (async, asyncio-first) — aligns with [hestia-design-revised-april-2026.md](hestia-design-revised-april-2026.md) Phase 4 note.
- Optional dev dependency: **`matrix-commander`** or **`matrix-nio`**-based test helper scripts (external to package, invoked from pytest or Makefile).

### 2.3 Configuration

New `MatrixConfig` dataclass (mirror style of `TelegramConfig` in `config.py`):

| Field | Purpose |
|-------|---------|
| `homeserver` | HTTPS base URL (e.g. `https://matrix.org`) |
| `user_id` | Bot MXID (`@hestia-bot:domain`) |
| `device_id` | Stable device name for token refresh |
| `access_token` | Bot access token (from login or admin) |
| `allowed_rooms` | List of room IDs or aliases allowed to talk to the bot (empty = deny all inbound) |
| `status_edit_min_interval_seconds` | Same idea as Telegram rate limit for `edit_message` |
| `sync_timeout_ms` | Long-poll tuning |

**Login story:** Obtain a token (Element dev tools, `matrix-nio` login once, or dedicated service user). Use **`.matrix.secrets.example.py`** → copy to **`.matrix.secrets.py`** (gitignored) — see **`docs/testing/CREDENTIALS_AND_SECRETS.md`**. Optional **`LOGIN_PASSWORD`** in that file supports Hermes-style manual re-login when the access token rotates; never commit the real file.

#### Runtime env vars

`MatrixConfig.from_env()` loads bot credentials from environment variables for `~/Hestia-runtime`-style deployments:

| Env variable | Maps to `MatrixConfig` field |
|--------------|------------------------------|
| `HESTIA_MATRIX_HOMESERVER` | `homeserver` (default: `https://matrix.org`) |
| `HESTIA_MATRIX_USER_ID` | `user_id` |
| `HESTIA_MATRIX_DEVICE_ID` | `device_id` (default: `hestia-bot`) |
| `HESTIA_MATRIX_ACCESS_TOKEN` | `access_token` |
| `HESTIA_MATRIX_ALLOWED_ROOMS` | `allowed_rooms` (comma-separated room IDs or aliases) |

Example `config.runtime.py` usage:

```python
from hestia.config import HestiaConfig, MatrixConfig

cfg = HestiaConfig.default()
cfg.matrix = MatrixConfig.from_env()
```

### 2.4 Session and room model

**Recommended default: one Matrix room ↔ one Hestia session** for predictable testing and isolation.

- `platform_user` = canonical room ID (`!abc:server`) or `!room:user` style string stored consistently.
- **Direct messages:** use the other party’s MXID as `platform_user`, or create a dedicated DM room and use its room ID (pick one rule and document it).

**Alternative (not recommended for v1):** one global room with thread-per-session — adds client complexity and inconsistent `matrix-nio` thread support across clients.

### 2.5 Platform ABC mapping

| `Platform` method | Matrix behavior |
|-------------------|-----------------|
| `name` | `"matrix"` |
| `start(on_message)` | Background sync loop; on text events in allowed rooms, call `on_message("matrix", platform_user, text)` |
| `stop()` | Cancel sync task, close client |
| `send_message(user, text)` | Send to room/user; return event ID as `msg_id` |
| `edit_message(user, msg_id, text)` | `m.room.message` edit (or replace) for status line |
| `send_error(user, text)` | Distinct prefix or message type so tests can detect errors |

**Status line:** Same orchestrator contract as Telegram: orchestrator passes `status_msg_id`; adapter rate-limits edits.

### 2.6 Confirmation callback (`ConfirmCallback`)

When destructive tools need approval:

1. Bot sends a message with **interactive elements** where the Matrix spec allows (buttons in supported clients via `m.room.message` + `org.matrix.msc3381.poll` is wrong — use **quick reply pattern** for v1: “reply YES `<nonce>` to confirm”).
2. Or use **slash-command / thread** convention documented for the test harness.
3. Long-term: MSC for buttons / integration with Element; track as follow-up.

For **integration tests**, prefer injecting a test double `ConfirmCallback` that auto-approves or reads from a queue, so tests do not depend on Element UI.

### 2.7 Scheduler integration

Scheduled tasks already run through the orchestrator with a response callback. For Matrix delivery:

- Persist **target room / user** on the scheduled task metadata (schema extension) **or** use the session’s `platform_user` from the session that created the task.
- `SchedulerEngine` invokes the same adapter `send_message` used by the Matrix runner.

Document which option is chosen in an ADR when implemented.

---

## 3. Security

- **Allowlist** `allowed_rooms` (and optional DM allowlist by MXID), same philosophy as Telegram `allowed_users`.
- **No plaintext secrets** in repository; env vars or `config.py` gitignored.
- Matrix JSON may contain **HTML**; strip or escape when feeding the model if `formatted_body` is used.
- Rate-limit outbound messages to avoid homeserver abuse flags.

---

## 4. Observability

- Structured log lines: `room_id`, `event_id`, `session_id` (no access token).
- Optional debug mode: log full event IDs only.

---

## 5. Integration test harness

### 5.0 Two Matrix identities (required mental model)

End-to-end and “real chat” tests involve **two different Matrix users**:

| Role | Who | Credentials | Purpose |
|------|-----|-------------|---------|
| **Bot (Hestia)** | The process running `hestia matrix` | `MatrixConfig`: `homeserver`, `user_id` (bot MXID), `access_token`, `device_id`, `allowed_rooms` | Receives events in allowlisted rooms, runs the orchestrator, sends replies **as this user**. |
| **Tester (driver)** | `matrix-commander`, a small `matrix-nio` script, or pytest fixture | **Separate** MXID + access token (and usually its own `device_id`) | Sends messages **into the same room** programmatically, reads the timeline for the bot’s reply, asserts content / latency. |

**Important:** The CLI tool used to drive tests is **not** “logging in as the bot.” It uses **its own** user account. Typical setup:

1. Register or use two accounts: `@hestia-test-bot:server` (Hestia) and `@hestia-test-client:server` (driver).
2. Create a **test room**, invite **both** users, ensure the bot’s `allowed_rooms` includes that room’s id.
3. Put **bot** credentials only in Hestia config (env or gitignored `config.py`).
4. Put **tester** credentials only in the driver (`matrix-commander` credentials file, or `MATRIX_TEST_USER_ACCESS_TOKEN` / similar for CI — names are convention, not hard-coded yet).

If the driver reused the bot token, you would only see the bot talking to itself and could not simulate a real human conversation or assert on “inbound from another user.”

### 5.1 Test layers

| Layer | What it proves | Speed |
|-------|----------------|-------|
| **Unit** | `MatrixAdapter` parses events, allowlist, edit throttling | Fast |
| **Component** | Fake `AsyncClient` / recorded HTTP responses | Fast |
| **E2E** | Real homeserver (Docker Synapse or matrix.org test account) | Slow, optional job |

### 5.2 CI recommendation

- **Default CI:** unit + component tests only.
- **Nightly / manual:** E2E job with secrets for **both** identities at minimum: e.g. `MATRIX_HOMESERVER`, `MATRIX_BOT_ACCESS_TOKEN`, `MATRIX_BOT_USER_ID`, `MATRIX_TEST_USER_ACCESS_TOKEN`, `MATRIX_TEST_USER_ID`, `MATRIX_TEST_ROOM_ID` (exact names up to harness; split bot vs tester explicitly).

### 5.3 Client options for E2E

- **`matrix-nio`** script (e.g. `scripts/matrix_smoke_send.py`) that logs in **as the tester user**, sends text to `MATRIX_TEST_ROOM_ID`, waits for a **reply event from the bot’s MXID** in the room timeline (timeout).
- **`matrix-commander`**: uses **its own** stored credentials (`~/.local/share/matrix-commander/credentials.json` or equivalent) for the **tester** account — **not** the same file/vars as Hestia’s bot token. Tests may shell out: start `hestia matrix` with bot config, then invoke `matrix-commander` as the other user to send/assert.

### 5.4 Full functional coverage and teardown (contract)

Automation should aim to exercise **every built-in tool** the Matrix platform allows (see README tool table), including the **`list_tools` / `call_tool`** meta path. For tools that **cannot succeed** on Matrix today (`write_file`, `terminal` — no confirmation UI), tests assert **denial or tool error**, not success.

**Memory:** `save_memory`, `search_memory`, and `list_memories` cover **untagged**, **tagged**, **multi-tag**, **list with tag filter**, and **FTS5 query shapes** (plain, AND/OR, quoted phrase where supported). There is **no** model-facing delete tool — tests **must** remove inserted rows in **`finally`** / fixture teardown via **`MemoryStore.delete`**, `hestia memory remove`, or a disposable test SQLite file. Use a unique tag or content prefix (e.g. `e2e_hestia_*`) so teardown is reliable.

**Executor specs:** **L11** (mock full tool matrix + memory + teardown), **L12** (live Matrix two-user E2E), **L13** (scheduler + Matrix), **L14** (manual smoke + runtime docs) — see **`docs/development-process/prompts/KIMI_LOOPS_L10_L14.md`** and **`docs/development-process/kimi-phase-queue.md`**.

---

## 6. Realistic example test scenarios

Each scenario below should become one or more **pytest** tests (names are suggestions). Preconditions: llama-server optional for pure adapter tests; full stack tests marked `@pytest.mark.e2e` and skipped without credentials.

### 6.1 Session lifecycle

| ID | Scenario | Steps | Assertions |
|----|----------|-------|--------------|
| M-01 | **First message cold start** | Send “hello” from allowed room | Bot replies; `SessionStore` has `platform=matrix` and `platform_user` = room id; exactly one active session |
| M-02 | **Second message same room** | Send follow-up in same room | Same session id; message history length increases |
| M-03 | **Two rooms two sessions** | Send from room A and room B | Two distinct `session_id`s; no cross-room history leak |

### 6.2 Orchestrator and tools

| ID | Scenario | Steps | Assertions |
|----|----------|-------|--------------|
| M-04 | **Tool round-trip** | Prompt that forces `current_time` or safe read-only tool | Reply contains tool output; turn reaches `DONE`; no `FAILED` |
| M-05 | **Denied destructive tool** | Prompt `run_terminal_cmd` / `write_file` with `confirm_callback=None` | Tool error text in thread; no shell execution; session still consistent |
| M-06 | **Memory round-trip** (if memory tools enabled) | “Remember that my favorite color is blue” then “What is my favorite color?” | `save_memory` + `search_memory` path; answer contains “blue” |
| M-07 | **Large reply artifacts** | Prompt producing output larger than inline cap | User-visible message references artifact handle; store contains blob |

### 6.3 Status and editing

| ID | Scenario | Steps | Assertions |
|----|----------|-------|--------------|
| M-08 | **Status message edits** | Slow enough turn that status updates fire | At least one `edit_message` call before final answer (mock or spy on client) |
| M-09 | **Rate limiting** | Rapid status updates | Adapter coalesces or drops edits under min interval (same test pattern as Telegram) |

### 6.4 Failure and recovery

| ID | Scenario | Steps | Assertions |
|----|----------|-------|--------------|
| M-10 | **Inference unreachable** | Stop llama-server; send message | User receives error via `send_error` or final message; turn `FAILED` persisted |
| M-11 | **Crash mid-turn** | Kill process during turn; restart `hestia matrix` | `recover_stale_turns` marks stale turn failed or resumes per policy; bot does not deadlock |

### 6.5 Scheduler (Matrix as delivery channel)

| ID | Scenario | Steps | Assertions |
|----|----------|-------|--------------|
| M-12 | **One-shot scheduled prompt** | From Matrix session, create task firing in N seconds (CLI or future Matrix command) | At fire time, message appears in target room with expected content |
| M-13 | **Cron tick** | Task with short cron in test harness | At least one execution logged; `last_run_at` updated |

### 6.6 Delegation (post–Phase 5)

| ID | Scenario | Steps | Assertions |
|----|----------|-------|--------------|
| M-14 | **Policy delegation** | Prompt that triggers `should_delegate` | Parent session receives `delegate_task` result envelope; subagent session `platform=subagent` |

### 6.7 Abuse and allowlist

| ID | Scenario | Steps | Assertions |
|----|----------|-------|--------------|
| M-15 | **Disallowed room** | Send from non-allowlisted room (if test homeserver permits) | No reply; no new session |
| M-16 | **Empty / whitespace** | Send blank body | No orchestrator call or graceful no-op |

### 6.8 Real-world “day in the life” composites

| ID | Scenario | Narrative | Assertions |
|----|----------|-----------|--------------|
| M-20 | **Morning briefing** | User: “Summarize my notes from memory tagged `work` and list today’s schedule” | Multiple tool calls; coherent final message; under token blow-up |
| M-21 | **Research task** | User: “Fetch https://example.com and tell me the title” | `http_get` used; title in reply; domain allowlist respected if configured |
| M-22 | **File assist (sandboxed)** | User asks to read a file under allowed_roots | Success; path outside roots returns denial message, not traceback |
| M-23 | **Follow-up after failure** | M-10 then fix server; new message | New turn succeeds; prior failure does not corrupt session |

---

## 7. Pytest structure (suggested)

```
tests/
  unit/
    test_matrix_adapter.py       # allowlist, parsing, rate limit
  integration/
    test_matrix_orchestrator.py  # MatrixAdapter + fake inference
  e2e/
    test_matrix_e2e.py           # @pytest.mark.e2e, requires env secrets
```

**Fixtures:**

- `matrix_bot_config` — Hestia’s `MatrixConfig` for subprocess under test
- `matrix_client` — `AsyncClient` connected to the **tester** user (driver), not the bot
- `hestia_matrix_process` — subprocess running `hestia matrix` with bot credentials (E2E only)
- `wait_for_matrix_reply(room_id, bot_mxid, timeout)` — poll timeline for an event **from** the bot after a message **from** the tester

---

## 8. Documentation deliverables (when implemented)

- `docs/DECISIONS.md` — ADR for Matrix adapter (homeserver assumptions, allowlist, session key = room id).
- `README.md` — short “Matrix dev setup” pointing to this file.
- `deploy/` — optional `hestia-matrix.service` example alongside Telegram.

---

## 9. Open decisions (to resolve at implementation time)

1. **Encrypted rooms:** support only unencrypted rooms for v1, or require `matrix-nio` e2ee store on disk?
2. **Reply threading:** use `m.relates_to` for threaded replies vs flat room timeline.
3. **Multi-device:** single bot device only vs separate `device_id` per deployment.
4. **Scheduler target:** schema field vs implicit session room.

---

**End of document**
