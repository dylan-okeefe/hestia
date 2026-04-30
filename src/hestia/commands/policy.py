"""Policy-related command implementations."""

from __future__ import annotations

import click

from hestia.app import AppContext
from hestia.core.clock import utcnow
from hestia.core.types import Session, SessionState, SessionTemperature
from hestia.policy.constants import CONTEXT_PRESSURE_THRESHOLD
from hestia.policy.default import DEFAULT_DELEGATION_KEYWORDS, DEFAULT_RESEARCH_KEYWORDS
from hestia.tools.capabilities import (
    EMAIL_SEND,
    MEMORY_READ,
    MEMORY_WRITE,
    NETWORK_EGRESS,
    SHELL_EXEC,
    WRITE_LOCAL,
)
from hestia.tools.registry import ToolNotFoundError


async def cmd_policy_show(app: AppContext) -> None:
    """Show current effective policy configuration."""
    cfg = app.config
    policy_engine = app.policy

    click.echo("=" * 60)
    click.echo("HESTIA EFFECTIVE POLICY")
    click.echo("=" * 60)
    click.echo("")

    # Reasoning budget
    click.echo("-" * 40)
    click.echo("REASONING BUDGETS")
    click.echo("-" * 40)
    click.echo(f"  Default: {cfg.inference.default_reasoning_budget} tokens")
    click.echo("  Subagent max: 1024 tokens (capped)")
    click.echo("")

    # Context window and budgets
    click.echo("-" * 40)
    click.echo("CONTEXT & COMPRESSION")
    click.echo("-" * 40)
    click.echo(f"  Context window: {policy_engine.ctx_window} tokens")
    synthetic_session = Session(
        id="diagnostic",
        platform="cli",
        platform_user="diagnostic",
        started_at=utcnow(),
        last_active_at=utcnow(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.HOT,
    )
    click.echo(f"  Turn token budget: {policy_engine.turn_token_budget(synthetic_session)} tokens")
    _pct = int(CONTEXT_PRESSURE_THRESHOLD * 100)
    click.echo(f"  Compression threshold: {_pct}% of budget")
    click.echo("")

    # Trust profile
    click.echo("-" * 40)
    click.echo("TRUST PROFILE")
    click.echo("-" * 40)
    click.echo(f"  Active preset: {cfg.trust.preset or '(custom — no preset name)'}")
    click.echo(f"  auto_approve_tools: {cfg.trust.auto_approve_tools or '(none)'}")
    click.echo(f"  scheduler_shell_exec: {cfg.trust.scheduler_shell_exec}")
    click.echo(f"  scheduler_email_send: {cfg.trust.scheduler_email_send}")
    click.echo(f"  subagent_shell_exec: {cfg.trust.subagent_shell_exec}")
    click.echo(f"  subagent_write_local: {cfg.trust.subagent_write_local}")
    click.echo(f"  subagent_email_send: {cfg.trust.subagent_email_send}")
    click.echo("")

    # Tool filtering by session type
    click.echo("-" * 40)
    click.echo("TOOL AVAILABILITY BY SESSION TYPE")
    click.echo("-" * 40)
    session_types = [
        ("interactive (cli)", "cli"),
        ("subagent", "subagent"),
        ("scheduler", "scheduler"),
    ]
    all_tools = app.tool_registry.list_names()
    now = utcnow()
    for label, platform in session_types:
        session = Session(
            id="policy-show",
            platform=platform,
            platform_user="policy",
            started_at=now,
            last_active_at=now,
            slot_id=None,
            slot_saved_path=None,
            state=SessionState.ACTIVE,
            temperature=SessionTemperature.HOT,
        )
        allowed = policy_engine.filter_tools(session, all_tools, app.tool_registry)
        blocked = set(all_tools) - set(allowed)
        click.echo(f"\n  {label}:")
        click.echo(f"    Allowed ({len(allowed)}): {', '.join(sorted(allowed))}")
        if blocked:
            blocked_with_reasons = []
            for tool in sorted(blocked):
                try:
                    meta = app.tool_registry.describe(tool)
                    caps = set(meta.capabilities)
                    if platform == "subagent":
                        if SHELL_EXEC in caps:
                            reason = "shell_exec"
                        elif WRITE_LOCAL in caps:
                            reason = "write_local"
                        elif EMAIL_SEND in caps:
                            reason = "email_send"
                        else:
                            reason = "other"
                    elif platform == "scheduler":
                        if SHELL_EXEC in caps:
                            reason = "shell_exec"
                        elif EMAIL_SEND in caps:
                            reason = "email_send"
                        else:
                            reason = "other"
                    else:
                        reason = "unknown"
                    blocked_with_reasons.append(f"{tool} ({reason})")
                except ToolNotFoundError:
                    blocked_with_reasons.append(tool)
            click.echo(f"    Blocked ({len(blocked)}): {', '.join(blocked_with_reasons)}")
    click.echo("")

    # Capabilities summary
    click.echo("-" * 40)
    click.echo("TOOL CAPABILITIES")
    click.echo("-" * 40)
    capability_tools: dict[str, list[str]] = {
        SHELL_EXEC: [],
        NETWORK_EGRESS: [],
        WRITE_LOCAL: [],
        MEMORY_READ: [],
        MEMORY_WRITE: [],
        EMAIL_SEND: [],
    }
    for tool in all_tools:
        try:
            meta = app.tool_registry.describe(tool)
            for cap in meta.capabilities:
                if cap in capability_tools:
                    capability_tools[cap].append(tool)
        except ToolNotFoundError:
            pass
    for cap, tools in capability_tools.items():
        if tools:
            click.echo(f"  {cap}: {', '.join(sorted(tools))}")
    click.echo("")

    # Delegation settings
    click.echo("-" * 40)
    click.echo("DELEGATION POLICY")
    click.echo("-" * 40)
    click.echo("  Delegation triggers:")
    click.echo("    - Tool chain > 5 calls")
    delegation_keywords = (
        cfg.policy.delegation_keywords
        if cfg.policy.delegation_keywords is not None
        else DEFAULT_DELEGATION_KEYWORDS
    )
    click.echo(f"    - Explicit delegation keywords: {', '.join(delegation_keywords)}")
    research_keywords = (
        DEFAULT_RESEARCH_KEYWORDS
        if cfg.policy.research_keywords is None
        else cfg.policy.research_keywords
    )
    click.echo(f"    - Research keywords: {', '.join(research_keywords)}")
    click.echo("    - Projected tool calls > 3")
    click.echo("  Subagent restrictions:")
    click.echo("    - Cannot delegate further (no recursion)")
    click.echo("    - Reduced reasoning budget")
    click.echo("")

    # Confirmation requirements
    click.echo("-" * 40)
    click.echo("CONFIRMATION REQUIREMENTS")
    click.echo("-" * 40)
    confirming = sorted(
        name
        for name in app.tool_registry.list_names()
        if app.tool_registry.describe(name).requires_confirmation
    )
    click.echo("  Tools requiring confirmation (interactive only):")
    if confirming:
        for name in confirming:
            click.echo(f"    - {name}")
    else:
        click.echo("    - (none)")
    click.echo("  Platforms with confirmation:")
    click.echo("    - cli: Yes (interactive prompt)")
    click.echo("    - telegram: No (tools requiring confirmation will fail)")
    click.echo("    - matrix: No (tools requiring confirmation will fail)")
    click.echo("    - scheduler: No (shell_exec blocked entirely)")
    click.echo("")

    # Retry policy
    click.echo("-" * 40)
    click.echo("RETRY POLICY")
    click.echo("-" * 40)
    click.echo(f"  Max attempts: {policy_engine.retry_max_attempts}")
    click.echo("  Transient errors (retry with backoff):")
    click.echo("    - InferenceTimeoutError")
    click.echo("    - InferenceServerError")
    click.echo("  Non-transient errors (fail immediately):")
    click.echo("    - All other exceptions")
    click.echo("")

    # Web search status
    click.echo("-" * 40)
    click.echo("WEB SEARCH")
    click.echo("-" * 40)
    if cfg.web_search.provider:
        click.echo(f"  Provider: {cfg.web_search.provider}")
        click.echo(f"  Max results: {cfg.web_search.max_results}")
    else:
        click.echo("  Web search: disabled")
    click.echo("")
