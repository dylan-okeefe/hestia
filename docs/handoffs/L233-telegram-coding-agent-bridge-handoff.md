# L233 Handoff — Telegram coding-agent bridge

Card: TaskView #70 (Pi + Flash-Next executor, Kimi reviewer; follow-up to #67/#68).
Branch: `feature/l233-telegram-coding-agent-bridge` (from develop, pushed).
Spec: `docs/development-process/loops/L233-telegram-coding-agent-bridge.md`

## What landed

| Phase | Status | Where |
|---|---|---|
| Ph1 — Pi installed, Strata provider wired | DONE (host) | `~/.pi/agent/models.json`, `settings.json` |
| Ph2 — small-coder + custom extensions + guardrails | DONE (host) | `~/.pi/agent/extensions/` (path-fence, git-autocommit, network-gate), `small-coder.json` |
| Ph3 — Telegram bridge | DONE (repo+host) | `src/hestia/platforms/agent_bridge.py`, `agent_bridge_runner.py`, `hestia coder-bot` CLI |
| Ph4 — TaskView MCP | DONE (host) | `~/.pi/agent/mcp.json` (61 tools, `pi mcp list` verified) |
| Ph5 — smoke ladder | **PENDING — needs Dylan live via Telegram** | rungs a–f below |
| Ph6 — systemd unit | DONE | `deploy/hestia-tg-agent.service`, installed enabled+started |
| Ph7 — Kimi reviewer loop | DONE (code) | in `agent_bridge.py` |

Commits: 575b8219 docs · 3d45b9ab config · bebda2ce bridge · fe7eba04 adapter
wiring · 3e069fb9 CLI · 38a0b005 tests · b513bec2 metrics · 1fa4492f deploy unit

## Pi provider config (verbatim, `~/.pi/agent/models.json`)

Provider `strata`, api `openai-completions`, baseUrl `http://127.0.0.1:8080/v1`,
model `qwen3.8-flash-next-iq3_s`, contextWindow 98304, maxTokens 8192,
promptCache short 300 / long 3600. Settings: thinking low, `thinking_budget`
4096 (NOTE: small-coder reads it from settings.json, NOT small-coder.json —
spec said otherwise; default is 4096 anyway), compaction on, retry maxRetries 2.

## small-coder source review (2026-10-21, v0.1.0)

Clean: no telemetry, no credential access, no install hooks. Kept ALL 20
extensions, with hardening:
- **`permissionMode: "auto"` pinned in `~/.pi/agent/small-coder.json`** — the
  package's bundled config ships `accept-all` (bash gating fully off). Do not
  let an install step overwrite it; verify after any `pi install/update`.
- **Built-in bash whitelist is porous** (`curl`, `wget`, `rm `, `pkill`,
  `pip install` prefix-matched; pipe-to-shell passes). Our `network-gate`
  extension blocks `webfetch`/`websearch`; the path-fence blocks file access
  outside the workspace. `bashAllow` only ADDS prefixes.
- Not using the `small-coder` bin: it forces `--no-extensions`, rewrites global
  settings, and disables pi's version check.
- Prompt-injection extensions (output-parser, quality-monitor, thinking-budget,
  context-watchdog, skill/knowledge-inject) steer the model without human
  review — acceptable with tools gated; surfaced on Telegram as status text.

## Custom extensions written (`~/.pi/agent/extensions/`)

1. **path-fence.ts** — read/write/edit confined to `~/hestia-tg-agent/`; bash
   commands referencing absolute paths outside the workspace (allowlist:
   /usr /bin /sbin /lib /lib64 /tmp /run /dev, ~/.cache ~/.local ~/.nvm ~/.pi
   ~/.small-coder) are blocked.
2. **git-autocommit.ts** — inits the workspace repo on first session; commits
   all changes at `agent_end` with a local identity (no global git config
   needed). Kimi reviewer diffs these.
3. **network-gate.ts** — blocks `webfetch`/`websearch` (the only network
   egress; websearch leaks queries to 3 third-party SearXNG hosts). Static
   small-coder `allowedTools` was NOT used because its exact-match gate would
   also kill `mcp__*` tools (TaskView MCP). `TG_AGENT_ALLOW_NETWORK=1` overrides.

Guardrail verification (all PASSED 2026-10-21): outside-workspace write
refused; workspace edit → commit `2f42bc7` landed; `ls; rm -rf ~/fence-canary`
refused + blocked, canary intact.

## Host state

- `hestia-tg-agent.service` (user unit): enabled+started. Token via
  `~/.config/hestia-tg-agent/token.env` (600). `HESTIA_TG_AGENT_CHATS=
  8550496999,8569861468` in the unit — Dylan chose to allow both IDs (spec
  said owner-only; tighten by editing the unit). NO Conflicts/Wants against
  hestia-serve or model services — it must survive them being stopped.
- `config.coder-bot.py` (untracked, ~/Hestia-runtime): bridge-enabled
  TelegramConfig + a valid InferenceConfig — required because the CLI builds
  AppContext for every command (inference client constructed but never
  connected; coder-bot never uses it).
- Deployed to ~/Hestia-runtime (merge of origin/feature/l233); runtime pytest
  2440 passed / 0 failed; hestia-serve restarted 2026-10-21 11:06 EDT, healthy.
- Dev worktree pre-existing issues (NOT ours, fail on develop too): numpy
  missing from dev venv → 1 test failure (voice pipeline) + 1 mypy error.

## Deviation notes

- kimi `--session` = `tg-agent-<slugified-workspace>` with `-review`/`-exec`
  suffixes (spec said `tg-agent-<workspace>`).
- Escalation hands kimi the most recent failed run's task text.
- Ph5 smoke ladder needs Dylan: (a) chat round-trip, (b) read-only workspace
  question, (c) write a script, (d) coding task with build/test, (e) long task
  (queue + prompt-cache follow-up), (f) mid-task steering.

## Upstream observations

Nothing outright buggy in Pi 1.3.0 RPC docs. Two notes: rpc.md's minimal
example uses `--no-session` (would defeat the PI_SESSION_ID checkpoint
extension — the bridge omits it); prompt-during-stream requires
`streamingBehavior: "steer"` (docs warn, bridge complies).

## Follow-ups (named)

- L234 candidates: Ph5 ladder results + tuning; voice notes on the coder bot
  (with the card #65 voice migration); `kimi web` persistent daemon; Pi Durable
  long-running sessions.
