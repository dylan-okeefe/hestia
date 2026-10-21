# L233 — Telegram coding-agent bridge (Pi RPC + Strata executor)

Spec source: Dylan's 7-phase spec (2026-10-21, TaskView card #70, follow-up to #67/#68).
Phases 1–2 (Pi install, provider wiring to Strata, small-coder + custom extensions,
guardrail verification) are DONE outside the repo. This loop covers the Hestia-side
code (Ph3), TaskView MCP (Ph4), the systemd unit (Ph6), and the Kimi reviewer loop
(Ph7). Ph5 (Telegram smoke ladder) needs Dylan live — deferred to post-review.

## Context the implementer needs

- Strata is LIVE and FROZEN at http://127.0.0.1:8080/v1 (OpenAI-compatible, model
  `qwen3.8-flash-next-iq3_s`, single inference slot + queue with 429+Retry-After,
  256K ctx). Do NOT restart/reconfigure/stop it. Agent traffic shares the slot by
  design; 429+Retry-After must be surfaced as "queued" status, never an error.
- Pi 1.3.0 (`@earendil-works/pi-coding-agent`) is installed globally (node 24).
  Version-exact docs: `/home/dylan/.nvm/versions/node/v24.18.0/lib/node_modules/@earendil-works/pi-coding-agent/docs/`
  — READ rpc.md, rpc-commands.md, json.md before coding the client.
- Pi agent-side setup is done and must be USED AS-IS: provider `strata` in
  `~/.pi/agent/models.json`, settings in `~/.pi/agent/settings.json`, small-coder
  package + custom extensions (path-fence, git-autocommit, network-gate) in
  `~/.pi/agent/extensions/`. The bridge spawns `pi --mode rpc` with cwd
  `~/hestia-tg-agent` (the fenced workspace; path-fence confines file tools there).
  Set env `PI_SESSION_ID=<chat-id>` per session (checkpoint extension keys on it).
- Telegram bot token lives in `~/.config/hestia-tg-agent/token.env` (mode 600,
  key `HESTIA_TG_BOT_TOKEN`). NEVER commit it or echo it into logs.
- Existing adapter: `src/hestia/platforms/telegram_adapter.py` (1237 lines,
  python-telegram-bot 22.7, asyncio). Text dispatch: `_handle_message` (~:861-912);
  `send_message` (:332), `edit_message` (:359, rate-limited), `set_typing` (:482),
  streaming exemplar `_make_stream_callback` (:514-579); `stop()` (:270);
  dep-injection setter pattern `set_voice_deps` (:206); tests pattern in
  `tests/unit/test_telegram_adapter.py` (mock `Application`/`Bot`/`Update`).
- Config: `TelegramConfig` (config.py:167-195), env prefix `TELEGRAM`, list fields
  parse as JSON via the env mixin.

## §1 — Bridge core (Hestia code)

New module `src/hestia/platforms/agent_bridge.py`:

1. `PiRpcClient` — asyncio wrapper around ONE persistent `pi --mode rpc` child per
   chat thread. Strict JSONL framing on LF only (read raw bytes, split on b"\n",
   strip trailing \r; do NOT use str line readers that split on U+2028/2029).
   Correlated commands via unique string `id`s. Read stdout continuously in a
   dedicated task (backpressure stalls the child). API: `start(cwd, name, env)`,
   `prompt(message) -> str` (id), `abort()`, `aclose()` (close stdin, await exit).
   Do NOT spawn per message.
2. `AgentBridge`:
   - `dict[platform_user, _ChatSession]` holding client + status message id +
     run-state. Route only chats in `agent_bridge_chats` (allowlist by
     platform_user exactly as `_handle_message` computes it); everything else
     falls through to the normal `_on_message` path.
   - First message for a chat spawns the child (cwd=`agent_bridge_workspace`,
     env `PI_SESSION_ID=<platform_user>`); subsequent messages go to the same
     child. A message arriving while a run is active is sent as another RPC
     `prompt` — Pi treats it as steering/follow-up per its settings (do not
     implement your own queue).
   - Status UX: on run start, `send_message` a status ("working…"), keep its id,
     `edit_message` it on progress events (model it on `_make_stream_callback`
     and `_handle_compact`; adapter rate limiting already built in). Final
     assistant answer = NEW `send_message`. `set_typing` around runs.
   - Map RPC retry/queue events (see json.md for the exact event names) to a
     "queued behind another task" status edit. Provider 429 handling is Pi's
     retry layer (`retry.maxRetries: 2` in settings); the bridge only displays.
   - Child exit mid-session: mark session broken, post a brief error message,
     respawn on next incoming message. `aclose()` terminates all children —
     called from `TelegramAdapter.stop()` alongside existing cancels.
3. `TelegramConfig` additions: `agent_bridge_enabled: bool = False`,
   `agent_bridge_chats: list[str] = []`, `agent_bridge_workspace: str = "~/hestia-tg-agent"`.
   All three must be read somewhere (§1.2 uses them; the CLI in §1.4 sets them).
4. `TelegramAdapter._handle_message`: after the workflow-pending check, before
   `_on_message` dispatch — if bridge enabled and `bridge.should_route(platform_user)`:
   `await bridge.handle(...)` then `return`. Attach bridge via a
   `set_agent_bridge()` setter mirroring `set_voice_deps`.
5. New CLI command `hestia coder-bot` (cli.py + wire in runners or a small
   dedicated runner): builds a `TelegramAdapter` from config with
   `agent_bridge_enabled=True` and `_on_message=None`, attaches the bridge, runs
   the polling loop until SIGINT/SIGTERM, then clean shutdown. It must NOT pull in
   the orchestrator, scheduler, or inference client — this service must keep
   working while `hestia serve` is down (that is its raison d'être).
6. Tests (new `tests/unit/test_agent_bridge.py`, follow the mock-bot patterns):
   routing allowlist (in/out), first-message spawns child, second message reuses,
   mid-run message becomes steering (assert second `prompt` command on same
   transport), status edit on progress + final as new message, child exit →
   respawn on next message, `stop()` closes children. Mock `PiRpcClient`'s
   transport; factor so subprocess spawning is injectable.
7. Commits: `feat(platforms): ...` conventional, one per logical piece.

## §2 — TaskView MCP for Pi (host config, not repo)

Pi reads MCP servers from `~/.pi/agent/mcp.json` (`pi mcp add` or edit the file;
validate with `pi mcp list`). Add server `taskview` = `npx -y taskview-mcp@1.45.0`
with env `TASKVIEW_URL`/`TASKVIEW_TOKEN` copied from `~/.kimi-code/mcp.json`
(treat the token as a secret: file perms 600, never in repo/logs). MCP list must
stay at TaskView only — each subagent session spawns MCP server processes and RAM
is tight (Strata pins ~53 GB of 64 GB).

## §3 — systemd unit (host config, not repo)

`~/.config/systemd/user/hestia-tg-agent.service`: runs `hestia coder-bot` from
`~/Hestia-runtime` (stable deployed code), `EnvironmentFile=%h/.config/hestia-tg-agent/token.env`,
`Restart=on-failure`, `RestartSec=5`, `StartLimitIntervalSec=300`,
`StartLimitBurst=5`, `LimitNOFILE=65536`. NO Conflicts/Wants against hestia-serve
or hestia-llama — this daemon must survive them being stopped. Unit starts
DISABLED; Dylan enables after reviewing benchmarks... (correction: after reviewing
the smoke ladder). Add the unit under `deploy/` in the repo too (without secrets).

## §4 — Kimi reviewer loop (Ph7)

In the bridge: after `agent_settled` for a run that produced new commits in the
workspace (`git -C <workspace> log` diff vs pre-run HEAD — capture pre-run HEAD at
run start), spawn ONCE:
`kimi -p "<review instructions> <git diff>" --plan --output-format stream-json --session tg-agent-<workspace>`
(kimi 2.2.0 at /home/dylan/.kimi-code/bin/kimi; `--plan` = read-only, the reviewer
must never touch files). Post the verdict to the chat as a new message. Dylan
approves or steers in-chat.

- Non-negotiable design rule: Flash-Next proposes, Kimi disposes — never the
  reverse. The reviewer never waits on Strata's queue (kimi uses its own cloud
  auth, not Strata); the executor never blocks on the reviewer's verdict.
- Escalation: a run that ends in error/failure twice in a row for the same chat →
  post "hand to Kimi?" offer; a "yes" reply runs kimi WITHOUT `--plan` to execute
  the task directly.
- Reviewer failure (kimi missing, nonzero exit) → log + skip review, never crash
  the bridge.

## Deferred (named follow-ups, not silently dropped)

- Ph5 smoke ladder via Telegram (needs Dylan live): rungs a–f.
- Voice notes on the coder bot (STT deferred with card #65 voice migration).
- `kimi web` persistent REST daemon instead of per-review spawn (spec's "later").
- Deploy-to-runtime + enabling the unit (Dylan's call after review).

## Handoff report requirements

Per-phase pass/fail, Pi provider config verbatim location, small-coder extensions
kept/disabled + why (source-review findings), custom extensions written (3),
systemd unit verbatim, latency numbers per ladder rung (when run), upstream-smelling
bugs. Report on TaskView card #70, linked to #67/#68.

## Critical rules recap

- Do NOT touch Strata or any running service. Everything reversible.
- 429/queue = wait + display "queued", never error to user.
- No secrets in repo/logs; token.env mode 600.
- Quality gates: `uv run pytest tests/unit/ tests/integration/ -q`,
  `uv run mypy src/hestia`, `uv run ruff check src/ tests/` (line length 120).
- Branch `feature/l233-telegram-coding-agent-bridge` from `develop`.
- No sync I/O in async paths; narrow excepts; every config field wired.
