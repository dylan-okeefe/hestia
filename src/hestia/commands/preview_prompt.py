"""Preview prompt assembly for diagnostic tuning.

Shows exactly what lands in the system prompt and how much budget
remains for conversation history at different context sizes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import click

from hestia.app import AppContext
from hestia.config import IdentityConfig
from hestia.context.builder import ContextBuilder
from hestia.core.inference import InferenceClient
from hestia.core.types import Message, Session, SessionState, SessionTemperature
from hestia.identity.compiler import IdentityCompiler
from hestia.memory.epochs import MemoryEpochCompiler
from hestia.policy.default import DefaultPolicyEngine


@dataclass
class _LayerInfo:
    name: str
    tokens: int
    truncated: bool
    text: str


@dataclass
class _Report:
    layers: list[_LayerInfo]
    budget: int
    empty_used: int
    history_used: int
    history_kept: int
    history_truncated: int
    ctx_len: int


async def _token_count(client: InferenceClient, text: str) -> int:
    tokens = await client.tokenize(text)
    return len(tokens)


async def _build_report(
    app: AppContext,
    identity_tokens: int | None,
    memory_tokens: int | None,
    context_length: int | None,
    sample_history_turns: int,
    platform: str | None = None,
    platform_user: str | None = None,
) -> _Report:
    cfg = app.config

    # --- overrides -----------------------------------------------------------
    ctx_len = context_length if context_length is not None else cfg.inference.context_length
    id_tokens = identity_tokens if identity_tokens is not None else cfg.identity.max_tokens
    mem_tokens = memory_tokens if memory_tokens is not None else cfg.memory.epoch_max_tokens

    # --- inference client for counting ---------------------------------------
    client = InferenceClient(cfg.inference.base_url, cfg.inference.model_name)

    # --- policy for budget ---------------------------------------------------
    policy = DefaultPolicyEngine(
        ctx_window=ctx_len,
        default_reasoning_budget=cfg.inference.default_reasoning_budget,
        trust=cfg.trust,
        config=cfg.policy,
        trust_overrides=cfg.trust_overrides,
    )

    # --- build prefixes ------------------------------------------------------
    effective_platform = platform or "preview"
    effective_platform_user = platform_user or "preview-user"

    identity_cfg = IdentityConfig(
        soul_path=cfg.identity.soul_path,
        max_tokens=id_tokens,
        recompile_on_change=cfg.identity.recompile_on_change,
    )
    identity_compiler = IdentityCompiler(identity_cfg)
    id_result = identity_compiler.compile()
    identity_text = id_result.text if id_result else ""
    identity_truncated = id_result.truncated if id_result else False

    # Memory epoch — scoped to the provided user when available.
    session = Session(
        id="preview-session",
        platform=effective_platform,
        platform_user=effective_platform_user,
        started_at=datetime.now(timezone.utc),
        last_active_at=datetime.now(timezone.utc),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )
    epoch_compiler = MemoryEpochCompiler(app.memory_store, max_tokens=mem_tokens)
    epoch = await epoch_compiler.compile(session)
    epoch_text = epoch.compiled_text
    epoch_truncated = epoch.token_estimate >= mem_tokens  # rough

    # Capabilities
    from hestia.app import _build_capabilities_prefix
    capabilities_text = ""
    if cfg.identity.capabilities_prefix_enabled:
        capabilities_text = _build_capabilities_prefix(cfg, app.tool_registry)

    # --- assemble context with overridden policy -----------------------------
    from hestia.app import DEFAULT_CALIBRATION_PATH
    cb = ContextBuilder.from_calibration_file(
        client,
        policy,
        getattr(app, "_calibration_path", None) or DEFAULT_CALIBRATION_PATH,
    )
    if identity_text:
        cb.set_identity_prefix(identity_text)
    if epoch_text:
        cb.set_memory_epoch_prefix(epoch_text)
    if capabilities_text:
        cb.set_capabilities_prefix(capabilities_text)

    # Build with empty history first to measure static overhead
    await cb.warm_up()
    empty_result = await cb.build(
        session=session,
        history=[],
        system_prompt=cfg.system_prompt,
        tools=[],
        new_user_message=Message(role="user", content="hello"),
    )

    # Build with sample history to show history fit
    sample_history: list[Message] = []
    for i in range(sample_history_turns):
        sample_history.append(Message(role="user", content=f"User message {i+1}"))
        sample_history.append(Message(role="assistant", content=f"Assistant reply {i+1}"))

    history_result = await cb.build(
        session=session,
        history=sample_history,
        system_prompt=cfg.system_prompt,
        tools=[],
        new_user_message=Message(role="user", content="Latest user message"),
    )

    # --- tokenise individual layers ------------------------------------------
    sys_tokens = await _token_count(
        client, f'{{"role":"system","content":"{cfg.system_prompt}"}}'
    )

    id_tokens_actual = 0
    if identity_text:
        id_tokens_actual = await _token_count(
            client, f'{{"role":"system","content":"{identity_text}"}}'
        )

    epoch_tokens_actual = 0
    if epoch_text:
        epoch_tokens_actual = await _token_count(
            client, f'{{"role":"system","content":"{epoch_text}"}}'
        )

    cap_tokens_actual = 0
    if capabilities_text:
        cap_tokens_actual = await _token_count(
            client, f'{{"role":"system","content":"{capabilities_text}"}}'
        )

    assembled_system = empty_result.messages[0].content
    assembled_tokens = await _token_count(
        client, f'{{"role":"system","content":"{assembled_system}"}}'
    )

    user_tokens = await _token_count(client, '{"role":"user","content":"hello"}')

    await client.close()

    layers = [
        _LayerInfo("system_prompt", sys_tokens, False, cfg.system_prompt),
        _LayerInfo("identity", id_tokens_actual, identity_truncated, identity_text),
        _LayerInfo("memory_epoch", epoch_tokens_actual, epoch_truncated, epoch_text),
        _LayerInfo("capabilities", cap_tokens_actual, False, capabilities_text),
        _LayerInfo("assembled_system", assembled_tokens, False, assembled_system),
        _LayerInfo("new_user_msg", user_tokens, False, "hello"),
    ]

    return _Report(
        layers=layers,
        budget=empty_result.tokens_budget,
        empty_used=empty_result.tokens_used,
        history_used=history_result.tokens_used,
        history_kept=len(sample_history) - history_result.truncated_count * 2,
        history_truncated=history_result.truncated_count,
        ctx_len=ctx_len,
    )


def _print_report(report: _Report, show_full: bool) -> None:
    click.echo("=" * 70)
    click.echo(f"Prompt preview (context_length={report.ctx_len})")
    click.echo("=" * 70)

    for layer in report.layers:
        if layer.name in ("assembled_system", "new_user_msg"):
            continue
        if not layer.text:
            continue
        truncated_marker = " [TRUNCATED]" if layer.truncated else ""
        click.echo(f"\n--- {layer.name} ({layer.tokens} tokens){truncated_marker} ---")
        if show_full:
            click.echo(layer.text)
        else:
            preview = layer.text[:400].replace("\n", " ")
            if len(layer.text) > 400:
                preview += " ..."
            click.echo(preview)

    click.echo("\n" + "-" * 70)
    click.echo("Budget summary")
    click.echo("-" * 70)
    click.echo(f"Per-turn token budget:     {report.budget:,} tokens")
    click.echo(f"Static overhead (no hist): {report.empty_used:,} tokens")
    click.echo(f"History budget remaining:  {report.budget - report.empty_used:,} tokens")
    click.echo(
        f"Sample history turns:      {report.history_kept // 2} kept / "
        f"{report.history_kept // 2 + report.history_truncated} total"
    )
    click.echo(f"With sample history used:  {report.history_used:,} tokens")
    click.echo(f"Headroom after sample:     {report.budget - report.history_used:,} tokens")
    click.echo("=" * 70)


async def cmd_preview_prompt(
    app: AppContext,
    identity_tokens: int | None,
    memory_tokens: int | None,
    context_length: int | None,
    show_full: bool,
    history_turns: int,
    platform: str | None = None,
    platform_user: str | None = None,
) -> None:
    report = await _build_report(
        app,
        identity_tokens=identity_tokens,
        memory_tokens=memory_tokens,
        context_length=context_length,
        sample_history_turns=history_turns,
        platform=platform,
        platform_user=platform_user,
    )
    _print_report(report, show_full=show_full)
