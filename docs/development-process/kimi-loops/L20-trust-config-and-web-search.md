# Kimi loop L20 — Trust profile config + Web search tool

## Review carry-forward

From L19 completion on 2026-04-17:

- Per-artifact metadata files still have no index/CRC. A manual file edit that writes invalid JSON surfaces as `JSONDecodeError` at read time, not `ArtifactNotFoundError`. **Not in scope for L20.** Track in a future loop if it keeps biting.
- `config.runtime.py` had to be extended by hand to wire MatrixConfig from `.matrix.secrets.py`. Consider adding a deploy-level example that reads all platform secrets from files or env vars. **Not in scope for L20** — will be folded into a future `hestia init` wizard loop.
- Tool-call traces don't show `save_memory` after `http_get` in the runtime yet. Probably because no memory saves have happened. Monitor; not a code issue.

**Design context:** See [`../reviews/capability-audit-april-17.md`](../reviews/capability-audit-april-17.md) for the full audit that motivated this loop. That document should already be committed to `develop` when this loop starts.

**Branch:** `feature/l20-trust-config-and-web-search` from **`develop`**.

---

## Goal

Two additions that together fix Hestia's biggest usability regression — that it can't actually automate tasks end-to-end on the platforms users care about:

1. **`TrustConfig`** — a new config dataclass with three preset profiles (`paranoid`, `household`, `developer`) that controls:
   - Which tools auto-approve without a `confirm_callback` on headless platforms (Telegram, Matrix, scheduler).
   - Whether the scheduler can call `SHELL_EXEC`-capable tools.
   - Whether subagents can call `SHELL_EXEC` or `WRITE_LOCAL` tools.

   Default is **paranoid** (current behavior). Operators opt into `household` explicitly in their `config.py`. This unblocks §1-3 of the capability audit without exposing a permissive surprise to new OSS users.

2. **`web_search` tool** with pluggable providers, shipped with a Tavily implementation. `WebSearchConfig.api_key = ""` by default means the tool is simply not registered — no billing setup is forced on users.

Version bump: **v0.3.0** (minor — new features, backward-compatible default behavior). **No release in this loop** — just develop work. Release is a separate loop when Dylan is ready to ship.

---

## §-1 — Create branch and capture baseline

```bash
git checkout develop
git pull origin develop
# Confirm the audit doc is on develop:
test -f docs/development-process/reviews/capability-audit-april-17.md || { echo "audit doc missing on develop"; exit 1; }

git checkout -b feature/l20-trust-config-and-web-search
uv run pytest tests/unit/ tests/integration/ -q
uv run ruff check src/ tests/
uv run mypy src/
```

Record the baseline pytest count — L19 closed with `~478 passed, 6 skipped`. The mypy baseline lives at `docs/development-process/mypy-baseline.txt`; don't regress it.

---

## §1 — Add `TrustConfig` dataclass

### File: `src/hestia/config.py`

Add a new dataclass above `HestiaConfig` (near the other sub-configs):

```python
@dataclass
class TrustConfig:
    """How much latitude to grant the agent in headless contexts.

    Hestia's threat model for personal-use deployments is "operator is the
    only user; trust the model to act on operator's behalf." This differs
    from multi-tenant SaaS. TrustConfig lets operators pick the posture that
    matches their deployment.

    Defaults here match the `paranoid` preset: safest posture for a fresh
    install or OSS download. Operators should explicitly opt into `household`
    or `developer` via `TrustConfig.household()` / `TrustConfig.developer()`
    in their `config.py`.
    """

    # Tools that auto-approve without a confirm_callback on headless platforms.
    # When a tool with requires_confirmation=True is called and no confirm_callback
    # is configured (Telegram, Matrix, scheduler), the tool runs anyway iff its
    # name is in this list.
    # Example for household use: ["terminal", "write_file"]
    auto_approve_tools: list[str] = field(default_factory=list)

    # Allow scheduler tick sessions to call SHELL_EXEC-capable tools.
    # When False (default), the policy engine strips shell_exec tools from the
    # model's available tool list during scheduler ticks.
    scheduler_shell_exec: bool = False

    # Allow subagent sessions to call SHELL_EXEC-capable tools.
    subagent_shell_exec: bool = False

    # Allow subagent sessions to call WRITE_LOCAL-capable tools.
    subagent_write_local: bool = False

    @classmethod
    def paranoid(cls) -> TrustConfig:
        """Strictest posture. Current default. Auto-approves nothing; scheduler
        and subagents cannot shell or write."""
        return cls()

    @classmethod
    def household(cls) -> TrustConfig:
        """Recommended posture for single-operator personal deployments.
        Auto-approves terminal and write_file on headless platforms;
        scheduler and subagents can shell and write."""
        return cls(
            auto_approve_tools=["terminal", "write_file"],
            scheduler_shell_exec=True,
            subagent_shell_exec=True,
            subagent_write_local=True,
        )

    @classmethod
    def developer(cls) -> TrustConfig:
        """Most permissive posture. Auto-approves everything;
        all capabilities available everywhere. Intended for development/testing
        only — do not use in a deployment exposed to other users."""
        return cls(
            auto_approve_tools=["*"],  # wildcard — matches any tool name
            scheduler_shell_exec=True,
            subagent_shell_exec=True,
            subagent_write_local=True,
        )
```

Add `trust: TrustConfig = field(default_factory=TrustConfig)` to `HestiaConfig`.

### Commit

```
feat(config): add TrustConfig for per-platform capability gates

Three presets: paranoid (default), household, developer. Paranoid matches
current behavior so this is a non-breaking default.
```

---

## §2 — Extend `PolicyEngine` protocol with `auto_approve`

The policy engine is the right home for trust decisions — it already owns `filter_tools`. Adding `auto_approve` keeps the orchestrator from needing its own copy of `TrustConfig`.

### File: `src/hestia/policy/engine.py`

Add to the `PolicyEngine` Protocol:

```python
def auto_approve(self, tool_name: str, session: Session) -> bool:
    """Whether a tool with requires_confirmation=True may run without
    a confirm_callback in the current session context.

    Returns True iff the trust profile has marked this tool as
    auto-approved for headless execution.
    """
    ...
```

### File: `src/hestia/policy/default.py`

Constructor takes `trust: TrustConfig | None = None`, defaulting to `TrustConfig()` (paranoid).

Implement:

```python
def auto_approve(self, tool_name: str, session: Session) -> bool:
    approved = self._trust.auto_approve_tools
    if "*" in approved:
        return True
    return tool_name in approved
```

Update `filter_tools` to gate scheduler/subagent blocks on trust flags:

```python
def filter_tools(self, session, tool_names, registry):
    from hestia.tools.capabilities import SHELL_EXEC, WRITE_LOCAL

    if session.platform == "subagent":
        blocked: set[str] = set()
        if not self._trust.subagent_shell_exec:
            blocked.add(SHELL_EXEC)
        if not self._trust.subagent_write_local:
            blocked.add(WRITE_LOCAL)
        if not blocked:
            return tool_names
        return [
            name for name in tool_names
            if not (set(registry.describe(name).capabilities) & blocked)
        ]

    if session.platform == "scheduler" or scheduler_tick_active.get():
        if self._trust.scheduler_shell_exec:
            return tool_names
        blocked = {SHELL_EXEC}
        return [
            name for name in tool_names
            if not (set(registry.describe(name).capabilities) & blocked)
        ]

    return tool_names
```

### Commit

```
feat(policy): wire TrustConfig into PolicyEngine

filter_tools now respects scheduler_shell_exec and subagent_* flags.
New auto_approve() method exposes per-tool auto-approval for the
orchestrator's confirmation gate.
```

---

## §3 — Wire `auto_approve` into the orchestrator's confirmation gate

### File: `src/hestia/orchestrator/engine.py`

At **both** enforcement sites (line ~641 and ~675), replace the current gate:

```python
if meta.requires_confirmation:
    if self._confirm_callback is None:
        return ToolCallResult(status="error", content="...", ...)
    confirmed = await self._confirm_callback(...)
    ...
```

with:

```python
if meta.requires_confirmation:
    if self._policy.auto_approve(tc.name, session):
        # Trust profile auto-approves this tool for this session context.
        pass
    elif self._confirm_callback is None:
        return ToolCallResult(
            status="error",
            content=(
                f"Tool '{tc.name}' requires user confirmation but no "
                "confirm_callback is configured and the trust profile does "
                "not auto-approve it. Add the tool to "
                "TrustConfig.auto_approve_tools, or run via a platform that "
                "supports confirmation (CLI)."
            ),
            artifact_handle=None,
            truncated=False,
        )
    else:
        confirmed = await self._confirm_callback(tc.name, tc.arguments or {})
        if not confirmed:
            return ToolCallResult(
                status="error",
                content="Tool execution was cancelled by user.",
                artifact_handle=None,
                truncated=False,
            )
```

Do the identical change at the meta-tool enforcement site (~line 641), using `inner_meta.requires_confirmation` and `name` / `arguments`.

**Important:** the `session` object needs to be in scope at both enforcement sites. Check: `_execute_tool` signature already takes `session` (or equivalent). If not, thread it in — don't pass `None`.

### Commit

```
feat(orchestrator): consult policy.auto_approve before rejecting on missing confirm_callback

Tools listed in TrustConfig.auto_approve_tools run without a callback.
Other tools continue to require a callback or return an actionable error
that points the operator at TrustConfig.
```

---

## §4 — Wire `TrustConfig` through CLI to `DefaultPolicy`

### File: `src/hestia/cli.py`

Find where `DefaultPolicy` is constructed (~line 303, search for `DefaultPolicy(`). Update to pass `trust=cfg.trust`:

```python
policy = DefaultPolicy(
    ctx_window=cfg.inference.context_length,
    default_reasoning_budget=cfg.inference.default_reasoning_budget,
    trust=cfg.trust,
)
```

Verify every constructor site — grep `DefaultPolicy\(` in `src/` and `tests/`. Tests that build a bare `DefaultPolicy()` should continue to work (trust defaults to paranoid). Tests that specifically test trust behavior should construct their own `TrustConfig`.

Also extend the `hestia config` output (`cli.py:1702-1716`) to print the trust profile:

```python
click.echo("")
click.echo("TRUST PROFILE")
click.echo(f"  auto_approve_tools: {cfg.trust.auto_approve_tools or '(none)'}")
click.echo(f"  scheduler_shell_exec: {cfg.trust.scheduler_shell_exec}")
click.echo(f"  subagent_shell_exec: {cfg.trust.subagent_shell_exec}")
click.echo(f"  subagent_write_local: {cfg.trust.subagent_write_local}")
```

### Commit

```
feat(cli): thread TrustConfig from HestiaConfig to DefaultPolicy

`hestia config` now prints the current trust profile for diagnostic clarity.
```

---

## §5 — Add `WebSearchConfig` dataclass

### File: `src/hestia/config.py`

Add a new dataclass alongside the others:

```python
@dataclass
class WebSearchConfig:
    """Configuration for the web_search tool.

    Default `provider=""` disables the tool entirely — it won't register
    in the tool registry if unconfigured. Operators opt in by setting
    provider + api_key in their config.py.
    """

    provider: str = ""  # "tavily" | "brave" | "" (disabled)
    api_key: str = ""
    max_results: int = 5
    include_raw_content: bool = False  # Tavily: fetch + extract main content
    search_depth: str = "basic"  # Tavily: "basic" | "advanced"
    time_range: str | None = None  # Tavily: "day" | "week" | "month" | "year" | None
```

Add `web_search: WebSearchConfig = field(default_factory=WebSearchConfig)` to `HestiaConfig`.

### Commit

```
feat(config): add WebSearchConfig for pluggable web search

Default provider="" means the tool won't register. Operators opt in by
setting provider + api_key explicitly.
```

---

## §6 — Implement `web_search` tool with Tavily provider

### File: `src/hestia/tools/builtin/web_search.py` (new)

```python
"""Web search tool with pluggable providers.

The tool is a factory — the CLI only registers it if WebSearchConfig is
populated. The function-level signature is provider-agnostic; provider
selection happens inside the factory based on config.
"""

from __future__ import annotations

from typing import Any

import httpx

from hestia.config import WebSearchConfig
from hestia.tools.builtin.http_get import SSRFSafeTransport
from hestia.tools.capabilities import NETWORK_EGRESS
from hestia.tools.metadata import tool


class WebSearchError(RuntimeError):
    """Raised when the configured provider fails."""


async def _tavily_search(
    query: str,
    *,
    api_key: str,
    max_results: int,
    include_raw_content: bool,
    search_depth: str,
    time_range: str | None,
    timeout_seconds: int,
) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": search_depth,
        "include_raw_content": include_raw_content,
    }
    if time_range is not None:
        payload["time_range"] = time_range

    async with httpx.AsyncClient(
        transport=SSRFSafeTransport(),
        follow_redirects=True,
        timeout=timeout_seconds,
    ) as client:
        response = await client.post("https://api.tavily.com/search", json=payload)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise WebSearchError(
                f"Tavily request failed: {exc.response.status_code} {exc.response.text[:200]}"
            ) from exc
        data = response.json()

    results = data.get("results") or []
    if not isinstance(results, list):
        raise WebSearchError("Tavily returned malformed response (no 'results' list)")
    return results


def _format_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return "No results."
    lines: list[str] = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "(untitled)")
        url = r.get("url", "(no url)")
        snippet = (r.get("content") or "").strip().replace("\n", " ")
        if len(snippet) > 500:
            snippet = snippet[:500].rstrip() + "..."
        lines.append(f"{i}. {title}\n   {url}\n   {snippet}")
    return "\n\n".join(lines)


def make_web_search_tool(config: WebSearchConfig) -> Any:
    """Build the web_search tool bound to the configured provider.

    Returns None if config.provider is empty or config.api_key is missing —
    caller should not register a None tool.
    """
    if not config.provider or not config.api_key:
        return None

    if config.provider != "tavily":
        raise ValueError(
            f"Unsupported web_search provider: {config.provider!r} "
            "(currently only 'tavily' is implemented; add a provider branch "
            "in web_search.py to extend)"
        )

    @tool(
        name="web_search",
        public_description=(
            "Search the web via the configured provider. Returns top results "
            "with title, URL, and snippet. Use this to find current information "
            "when you don't already have a specific URL to fetch."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (natural language, keywords, or a question).",
                },
                "max_results": {
                    "type": "integer",
                    "description": (
                        "How many results to return. Default from config "
                        f"({config.max_results})."
                    ),
                },
                "time_range": {
                    "type": "string",
                    "description": (
                        "Restrict to a recency window: 'day', 'week', 'month', or 'year'. "
                        "Omit for any time."
                    ),
                },
            },
            "required": ["query"],
        },
        max_inline_chars=6000,
        tags=["network", "builtin"],
        capabilities=[NETWORK_EGRESS],
    )
    async def web_search(
        query: str,
        max_results: int | None = None,
        time_range: str | None = None,
    ) -> str:
        """Run a web search via the configured provider."""
        effective_max = max_results if max_results is not None else config.max_results
        effective_time = time_range if time_range is not None else config.time_range
        try:
            results = await _tavily_search(
                query,
                api_key=config.api_key,
                max_results=effective_max,
                include_raw_content=config.include_raw_content,
                search_depth=config.search_depth,
                time_range=effective_time,
                timeout_seconds=30,
            )
        except WebSearchError as exc:
            return f"Web search failed: {exc}"
        except httpx.HTTPError as exc:
            return f"Web search transport error: {type(exc).__name__}: {exc}"
        return _format_results(results)

    return web_search
```

### File: `src/hestia/tools/builtin/__init__.py`

Ensure `make_web_search_tool` is exported alongside the other factories.

### Commit

```
feat(tools): add web_search builtin with Tavily provider

Factory pattern — tool only registers when WebSearchConfig is populated.
Uses the existing SSRFSafeTransport so the same safety guarantees as
http_get apply to search requests.
```

---

## §7 — Register `web_search` in CLI when configured

### File: `src/hestia/cli.py`

Find where the tool registry is built (search `ToolRegistry(` or `registry.register(`). Add:

```python
from hestia.tools.builtin.web_search import make_web_search_tool

web_search_tool = make_web_search_tool(cfg.web_search)
if web_search_tool is not None:
    tool_registry.register(web_search_tool)
```

Place this after the existing tool registrations so disabled web search doesn't surprise anyone.

Also extend the `hestia config` output:

```python
if cfg.web_search.provider:
    click.echo(f"  Web search: {cfg.web_search.provider} ({cfg.web_search.max_results} results)")
else:
    click.echo("  Web search: disabled")
```

### Commit

```
feat(cli): register web_search tool when WebSearchConfig is populated

`hestia config` reports web search status for diagnostic clarity.
```

---

## §8 — Tests

### File: `tests/unit/test_trust_config.py` (new)

Cover:
- Default `TrustConfig()` matches `paranoid()` (same field values).
- `household()` has the expected auto-approve tools and flags.
- `developer()` has wildcard and all flags True.

### File: `tests/unit/test_policy.py` (extend)

Add tests:
- `DefaultPolicy(trust=TrustConfig.paranoid()).auto_approve("terminal", session)` → False.
- `DefaultPolicy(trust=TrustConfig.household()).auto_approve("terminal", session)` → True.
- `DefaultPolicy(trust=TrustConfig.household()).auto_approve("write_file", session)` → True.
- `DefaultPolicy(trust=TrustConfig.household()).auto_approve("some_other_tool", session)` → False.
- `DefaultPolicy(trust=TrustConfig.developer()).auto_approve("any_tool_name", session)` → True (wildcard).
- `filter_tools` for scheduler:
  - paranoid → shell_exec tools stripped (existing behavior).
  - household → shell_exec tools retained.
- `filter_tools` for subagent:
  - paranoid → shell_exec and write_local both stripped.
  - household → both retained.
  - Partial config `subagent_shell_exec=True, subagent_write_local=False` → only write_local stripped.

### File: `tests/unit/test_orchestrator_confirmation.py` (new or extend existing orchestrator test)

Add tests that the orchestrator:
- Refuses a `requires_confirmation=True` tool when policy doesn't auto-approve and no callback is configured.
- Runs a `requires_confirmation=True` tool when policy auto-approves, even without a callback.
- Uses the callback when present, regardless of auto-approve state.

### File: `tests/unit/test_web_search.py` (new)

- `make_web_search_tool(WebSearchConfig())` returns `None` (no provider configured).
- `make_web_search_tool(WebSearchConfig(provider="tavily", api_key="k"))` returns a callable tool.
- `make_web_search_tool(WebSearchConfig(provider="unsupported", api_key="k"))` raises `ValueError`.
- Mock `httpx.AsyncClient.post` to return a canned Tavily response; assert `web_search("test")` returns formatted output containing titles/URLs.
- Mock `post` to return HTTP 401; assert `web_search` returns a string starting with "Web search failed:".
- Result formatter handles empty `results` list.

**Use `respx` or `httpx.MockTransport`** — do NOT hit real Tavily in tests. Add `respx` to `[tool.uv.dev-dependencies]` in `pyproject.toml` if not already present.

### Run

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run ruff check src/ tests/
uv run mypy src/
```

All green; mypy baseline unchanged.

### Commit

```
test: cover TrustConfig presets, policy gates, orchestrator auto-approve,
and web_search Tavily adapter
```

---

## §9 — Documentation

### File: `README.md`

Add a new section after the existing "Giving Hestia a personality" section (before the configuration reference):

```markdown
## Trust profiles

Hestia's default posture is strict: `terminal` and `write_file` both require
explicit user confirmation, the scheduler cannot call shell commands, and
subagents cannot shell or write files. This is safe for a fresh install, but
it's often more restrictive than you want for a single-operator personal
deployment.

Three presets live in `TrustConfig`:

- **`TrustConfig.paranoid()`** (default) — current behavior. Every `terminal`
  or `write_file` call on Telegram/Matrix/scheduler is blocked unless you wire
  a custom confirm callback. Scheduler and subagents can't shell or write.

- **`TrustConfig.household()`** (recommended for personal use) —
  auto-approves `terminal` and `write_file` on headless platforms, lets the
  scheduler run shell commands, lets subagents shell and write.

- **`TrustConfig.developer()`** — auto-approves everything. Dev/test only.

Opt in inside your `config.py`:

```python
from hestia.config import HestiaConfig, TrustConfig
config = HestiaConfig(
    ...,
    trust=TrustConfig.household(),
)
```

See `hestia config` for the active profile.
```

Add a "Web search" subsection near the tool documentation:

```markdown
### Web search

Hestia ships a `web_search` tool that activates when you configure a provider
in your `config.py`:

```python
from hestia.config import HestiaConfig, WebSearchConfig
config = HestiaConfig(
    ...,
    web_search=WebSearchConfig(
        provider="tavily",
        api_key="tvly-...",   # https://tavily.com/ — free tier is 1000/month
        max_results=5,
    ),
)
```

Tavily is the only built-in provider today. Without a configured provider,
the tool simply isn't registered — the model won't see it in its tool list.
Combined with `http_get`, this gives Hestia search-then-fetch capability for
daily research and news tasks.
```

### File: `CHANGELOG.md`

Add an `[Unreleased]` section above `[0.2.2]`:

```markdown
## [Unreleased]

### Added
- `TrustConfig` with three preset profiles (paranoid, household, developer)
  for per-platform capability gates. Default is paranoid — no behavior change
  for existing installs.
- `web_search` builtin tool with a Tavily provider. Disabled by default;
  opt in via `WebSearchConfig` in `config.py`.
- `hestia config` now reports the active trust profile and web search status.

### Changed
- `DefaultPolicy.filter_tools` now gates scheduler SHELL_EXEC and subagent
  SHELL_EXEC/WRITE_LOCAL restrictions on `TrustConfig` flags. Default
  behavior unchanged.
- `Orchestrator` consults `PolicyEngine.auto_approve()` before rejecting a
  `requires_confirmation` tool with a missing confirm_callback.
```

### File: `deploy/example_config.py`

Add a commented-out `trust=TrustConfig.household()` line so operators see the pattern when customizing.

### Commit

```
docs: trust profile + web search sections in README; CHANGELOG [Unreleased]
```

---

## §10 — Version bump

### File: `pyproject.toml`

Bump version to `0.3.0`:

```toml
version = "0.3.0"
```

### File: `src/hestia/__init__.py`

If there's a `__version__` constant, bump it to match.

### Commit

```
chore: bump version to 0.3.0
```

---

## §11 — Final verification

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run ruff check src/ tests/
uv run mypy src/

# Smoke: can the tool registry build with WebSearchConfig populated?
HESTIA_TEST=1 uv run python -c "
from hestia.config import HestiaConfig, WebSearchConfig, TrustConfig
cfg = HestiaConfig(
    web_search=WebSearchConfig(provider='tavily', api_key='test'),
    trust=TrustConfig.household(),
)
from hestia.tools.builtin.web_search import make_web_search_tool
t = make_web_search_tool(cfg.web_search)
assert t is not None, 'web_search should register'
print('OK: web_search registered, trust =', cfg.trust)
"

# Smoke: disabled config does not register
uv run python -c "
from hestia.config import WebSearchConfig
from hestia.tools.builtin.web_search import make_web_search_tool
assert make_web_search_tool(WebSearchConfig()) is None
print('OK: unconfigured web_search yields None')
"

# No new mypy regressions
diff <(uv run mypy src/ 2>&1 | grep -E 'error:' | sort) <(sort docs/development-process/mypy-baseline.txt) || echo "(may be empty if baseline format matches)"
```

Push the branch:

```bash
git push -u origin feature/l20-trust-config-and-web-search
```

**Do NOT merge to develop.** This is a feature loop — Dylan + Cursor review the PR before merge.

---

## Handoff

Write `.kimi-done` (do **not** commit):

```
HESTIA_KIMI_DONE=1
SPEC=docs/development-process/kimi-loops/L20-trust-config-and-web-search.md
LOOP=L20
BRANCH=feature/l20-trust-config-and-web-search
PYTEST_BASELINE=<from §-1>
PYTEST_FINAL=<from §11>
MYPY_FINAL_ERRORS=<from §11>
TRUST_CONFIG_WIRED=done
WEB_SEARCH_TAVILY=done
VERSION_BUMP=0.3.0
GIT_HEAD_BRANCH=<rev-parse HEAD>
```

---

## Critical rules recap

1. **No secrets.** Tavily `api_key` must NEVER enter a commit. Tests mock the HTTP layer — no real API calls.
2. **Paranoid is the default.** `TrustConfig()` with no args must produce the current behavior exactly. Any test that used to pass a default `DefaultPolicy()` must still pass.
3. **`web_search` must be conditional.** An unconfigured `WebSearchConfig` must produce a `None` tool; the CLI must not register it. Tests must cover this.
4. **Session scope at confirmation gate.** The orchestrator's auto-approve check requires `session` at both enforcement sites. If the current signature doesn't pass `session` through, plumb it — don't pass `None` and don't special-case.
5. **One commit per section.** Order matters: config → policy → orchestrator → CLI → web_search config → web_search tool → CLI registration → tests → docs → version.
6. **All tests green after every commit.** If a commit breaks tests even temporarily, restructure so the same logical change is squashed into a single, green commit.
7. **No release in this loop.** Merge strategy (develop vs. feature branch vs. main) and release tagging belong to a later loop. This loop produces a feature branch only.
8. **`.kimi-done` last.** Only after §11 verification passes cleanly.
9. **Stop and report immediately on any phase failure.** Especially §3 (orchestrator gate) — getting that wrong breaks the confirmation UX across every platform.
