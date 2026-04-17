# Capability & Usability Audit — April 17, 2026

**Scope:** Review of security/permission drift that is degrading Hestia's core
value proposition (being an actually useful personal assistant). Includes
recommendations for web search, confirmation flow, scheduler permissions, and
setup simplification.

**Context:** A real-world failure triggered this audit. When asked to set up a
weather-automation cron job via Telegram/Matrix, Hestia responded:

> "I can't run terminal commands directly (the system requires manual
> confirmation for shell access). This means I can write the script for you,
> but you'll need to run it and set up the cron job yourself."

This response is *technically correct* given the current code, but it makes
Hestia functionally equivalent to a chat window that outputs snippets — not the
personal assistant the product is supposed to be.

---

## 1. The Confirmation Deadlock (Primary Capability Bug)

### What the code does

Two tools declare `requires_confirmation=True`:

- `src/hestia/tools/builtin/terminal.py:28` — `terminal`
- `src/hestia/tools/builtin/write_file.py:24` — `write_file`

`Orchestrator._execute_tool` (engine.py:641, 675) enforces that if a tool
requires confirmation and no `confirm_callback` is configured, the tool returns
an error *without even attempting to run*. The error message is:

> "Tool 'terminal' requires user confirmation but no confirm_callback is
> configured on this orchestrator."

The model then interprets that error and politely gives up.

### Who wires the callback

| Platform  | `confirm_callback` wired? | Source                     |
|-----------|---------------------------|----------------------------|
| CLI (`hestia chat`) | Yes (stdin prompt)  | `cli.py:143` CliConfirmHandler |
| Telegram  | **No** — TODO             | `cli.py:1146-1148`         |
| Matrix    | **No** — TODO             | `cli.py:1276-1278`         |
| Scheduler | **No** — intentional      | `cli.py:1007-1009`         |

So `terminal` and `write_file` *cannot run at all* via Telegram, Matrix, or
scheduled tasks. This is the direct cause of the weather-automation failure.

### Severity

High. This blocks the product's two most important use cases:

1. **Cron-triggered daily work** (research briefings, weather summaries, backup
   scripts, log rotation, any "do this every morning" task) — impossible
   without shell access.
2. **Conversational automation via Telegram/Matrix** (the main UX on mobile) —
   crippled for anything beyond Q&A.

### Recommended fix

Two options, either/both:

**Option A: Wire real confirmation for Telegram/Matrix.**
The TODOs at `cli.py:1148` and `cli.py:1278` describe the shape:
- Telegram: inline keyboard with ✅/❌ callback buttons (python-telegram-bot
  supports this natively)
- Matrix: reply-with-text pattern (`matrix-nio` reply hooks)
Effort: roughly one feature branch, 1-2 Kimi loops.

**Option B: Per-tool auto-approve via config (recommended primary path).**
Add a trust profile to config — see §4 — that lets the operator decide "for my
personal Hestia, `terminal` and `write_file` don't require confirmation when
invoked from Telegram/Matrix/scheduler." Default is to keep current behavior so
OSS users don't get a permissive surprise.

Both fit together: confirmation UI for operators who want it, auto-approve for
operators who know they're the only user.

---

## 2. Scheduler Cannot Run Shell (Secondary Capability Bug)

### What the code does

`src/hestia/policy/default.py:171-178`:

```python
if session.platform == "scheduler" or scheduler_tick_active.get():
    # Scheduler: block shell_exec for headless safety
    blocked = {SHELL_EXEC}
    return [
        name
        for name in tool_names
        if not (set(registry.describe(name).capabilities) & blocked)
    ]
```

This is a *hard policy filter*, not a confirmation gate. Scheduled tasks are
handed a tool list with `terminal` removed before the model even sees it. The
model doesn't get "I can't run terminal" — it gets "terminal isn't a tool that
exists." Which is worse, because it can't explain the limitation.

### Severity

High. Kills the cron-automation use case even if §1 is fixed.

### Recommended fix

Gate on config. Replace with:

```python
if (session.platform == "scheduler" or scheduler_tick_active.get()) and not trust.scheduler_shell_exec:
    ...
```

Default `scheduler_shell_exec=False` to preserve current behavior for fresh
installs; household profile flips it to `True`.

---

## 3. Subagents Are Over-Restricted

### What the code does

`src/hestia/policy/default.py:162-169`:

```python
if session.platform == "subagent":
    # Subagents: block shell_exec and write_local
    blocked = {SHELL_EXEC, WRITE_LOCAL}
    return [
        name
        for name in tool_names
        if not (set(registry.describe(name).capabilities) & blocked)
    ]
```

The `delegate_task` tool spins up a subagent to handle a specific task,
returning a bounded summary. This is the "offload the long tool chain" feature
documented in README §Subagent delegation. But subagents can't shell and can't
write files — which defeats many reasonable delegations:

- "Pull the last week of git log and summarize the security-relevant commits" —
  needs shell.
- "Research X and save a markdown report I can read later" — needs
  write_file.

### Severity

Medium. The feature still has uses (pure-reasoning offloads, web research
where http_get is enough), but the subagent pattern is strictly less powerful
than the parent. This is the opposite of what's useful — parents should
*delegate messy work* to subagents, which currently can't do the messiest work.

### Recommended fix

Same pattern: gate on config. Operator decides. Default restrictive (current
behavior), household profile permissive.

---

## 4. Proposed: Trust Profile Config

Introduce a new config dataclass:

```python
@dataclass
class TrustConfig:
    """How much latitude to grant the agent in headless contexts.

    Hestia's threat model for a personal-use deployment is "operator is the
    only user; trust the model to act on operator's behalf." This differs from
    a multi-tenant SaaS. TrustConfig lets operators pick the posture that
    matches their deployment.
    """

    # Tools that auto-approve without a confirm_callback on headless platforms.
    # Applies to Telegram, Matrix, scheduler, and any other context where
    # confirm_callback is None.
    auto_approve_tools: list[str] = field(default_factory=list)
    # Example: ["terminal", "write_file"] for household use.

    # Allow scheduler tick sessions to call shell_exec-capable tools.
    scheduler_shell_exec: bool = False

    # Allow subagents to call shell_exec / write_local-capable tools.
    subagent_shell_exec: bool = False
    subagent_write_local: bool = False
```

Expose as `HestiaConfig.trust`. Wire the three gates:

1. `Orchestrator._execute_tool` checks `auto_approve_tools` before failing on
   missing confirm_callback.
2. `DefaultPolicy.filter_tools` respects the scheduler/subagent flags.

Ship three preset helpers in `config.py`:

```python
TrustConfig.paranoid()    # current behavior (default)
TrustConfig.household()   # recommended for personal use
TrustConfig.developer()   # everything auto-approved
```

Document the tradeoffs clearly in README so users make an informed choice.

---

## 5. Web Search Tool — Missing

### What exists today

- `http_get` (good): fetches a URL's content, with proper SSRF protection.
  Requires the model to *already know the URL*.
- No search tool at all. No Tavily, Brave, DuckDuckGo, or SerpAPI integration.

### Why this matters

"What's the weather in Seattle?" currently requires either:
- The model hallucinating a URL (brittle)
- Hardcoding a weather API config per site
- The operator pre-teaching it specific endpoints in SOUL.md

Real-world tasks the operator actually asks about — "find the latest reviews
of X", "what's the news on Y", "summarize recent papers on Z" — require
*search-then-fetch*, not just fetch.

### Recommended implementation

Add a `web_search` builtin tool with pluggable providers:

```python
@dataclass
class WebSearchConfig:
    provider: str = "tavily"  # tavily | brave | disabled
    api_key: str = ""
    max_results: int = 5
    include_raw_content: bool = False  # Tavily: fetch + extract main content
    time_range: str | None = None       # "day" | "week" | "month"
```

**Tavily recommended as the default provider:**
- Free tier: 1000 searches/month
- Returns cleaned snippets + optional full-content extraction
- Designed for LLM consumers (much better than raw SERP APIs)
- Python client trivial (plain HTTP JSON)

**Brave Search as the secondary provider:**
- 2000 free searches/month, broader (web + news + images)
- Better for "what's happening right now" queries

Tool signature:
```python
@tool(
    name="web_search",
    public_description="Search the web and return top results with snippets.",
    max_inline_chars=6000,
    capabilities=[NETWORK_EGRESS],
)
async def web_search(query: str, max_results: int = 5, time_range: str | None = None) -> str:
    """Search the web via configured provider. Returns title/url/snippet for each result."""
```

Combined with `http_get`, this closes the loop: search → pick relevant URL →
fetch → summarize → save to memory or artifact. All the steps for "daily
research" now work.

### Secondary consideration: local private-IP policy

`http_get` blocks private IP ranges (10/8, 192.168/16, etc.) as SSRF defense.
For a home-lab setup this can block legitimate uses: fetching from a local
Home Assistant instance, an internal wiki, a homelab RSS reader. Consider:

```python
@dataclass
class NetworkConfig:
    allow_private_ip_ranges: list[str] = field(default_factory=list)
    # e.g. ["192.168.1.0/24", "10.0.0.0/24"] for explicit lab subnets
```

Opt-in only — keeps the default safe while letting the operator punch holes
for their specific LAN.

---

## 6. Setup Friction

Dylan noted setup could be simpler. Current state:

- Config is `config.py` — a Python file that executes arbitrary code on load
  (`HestiaConfig.from_file` uses `exec_module()`). This is a *design choice*
  for personal-use flexibility and is noted in README under security concerns.
- No interactive setup wizard.
- No default SOUL.md template.
- No "did your llama-server start correctly?" diagnostic.

### Recommended additions

**`hestia init`** — interactive setup that writes a starter `config.py` based
on answers to a handful of questions:

1. "What's your llama-server URL?" (default http://localhost:8001)
2. "Model GGUF name?" (fetches via /v1/models endpoint if reachable)
3. "Which platforms do you want active?" (CLI / Telegram / Matrix)
4. "Trust profile?" (paranoid / household / developer)
5. "Web search provider + API key?" (optional)
6. "Where should Hestia write files?" (default $HOME/hestia-workspace)

Generates `config.py`, `SOUL.md` template, and `.hestia/` layout in one go.
Plus prints a "try this to verify" diagnostic: `hestia check` that pings
llama-server, runs a quick turn, writes and reads a test file.

**`hestia check`** — diagnostic command already hinted at by `cli.py:1702-1716`
showing policy and budget. Extend to actively probe each configured subsystem.

**Config file split.** Consider supporting TOML alongside the Python
`config.py`. TOML is:
- Safer (no code execution)
- Easier for non-developers
- Well-supported in stdlib (`tomllib`)

Keep `config.py` as the advanced option for operators who want conditional
config, environment-derived values, etc. Document both.

---

## 7. Summary of Drift

The core insight: **Hestia's threat model is "operator is the only user."**
Every restriction built around "what if an adversary prompt-injects the
agent?" is the wrong frame for this product. The right frame is "what
*unexpected* thing could the model do that I'd regret?"

Current defaults skew toward SaaS-style multi-tenant posture, which produces
friction the operator can't easily remove. Symptoms:

- Model refuses obvious, useful work because confirmation infrastructure
  isn't wired.
- Scheduled tasks silently lack capability the operator explicitly wanted
  them to have.
- Subagent delegation pattern cannot accomplish what it's designed for.
- Missing web search makes "research" tasks require operator knowledge the
  model should be able to gather itself.

None of these are bugs in the security model — they're over-application of a
safety posture to a single-operator product. **The fix isn't to remove the
safety, it's to make the posture configurable with sensible defaults for
personal use.**

---

## 8. Prioritized Fix Order

Suggested order for the next Kimi loops:

| Loop | Work | Why |
|------|------|-----|
| L20  | Add `TrustConfig` + wire three gates (auto-approve, scheduler shell, subagent caps) | Unblocks §1-3. Small, self-contained, no external deps. |
| L21  | Add `web_search` tool with Tavily provider + `WebSearchConfig` | Unlocks "research" use cases. Tavily free tier means no billing setup. |
| L22  | Telegram inline-keyboard confirmation callback | Lets operators who *want* confirmation prompts have them on mobile. |
| L23  | `hestia init` wizard + optional TOML config support | Setup simplification; not urgent but big UX win. |
| L24  | Optional: Matrix reply-pattern confirmation callback | Only if Matrix is the primary UX. Else defer. |
| L25  | Optional: `allow_private_ip_ranges` for homelab integrations | Only if operator has LAN services to integrate. |

L20 and L21 together would transform the product: L20 unblocks the current use
cases, L21 makes them 10x more useful.

---

## 9. Open Questions for the Operator

Before implementation, worth deciding:

1. **Trust profile default** — ship "paranoid" as default to protect new OSS
   users, or "household" to match product intent? My vote: "paranoid" is the
   right OSS default; flag it loudly in the quickstart with a "for single-user
   home setups, run `hestia config set-profile household` to reduce friction."

2. **Web search provider default** — Tavily (LLM-optimized) or Brave (broader
   web coverage, higher free quota)? My vote: Tavily. Much better snippets
   for a local model.

3. **Confirmation UI scope** — build for both Telegram and Matrix, or pick
   one? Depends on operator's actual usage. If Telegram is primary, do that
   first.

4. **Private-IP allowlist** — deferred or needed now? Depends whether there
   are homelab integrations the operator wants (Home Assistant, Jellyfin,
   internal RSS, etc.).
