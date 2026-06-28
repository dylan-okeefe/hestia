"""Meta-command handler for Hestia CLI REPL."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from hestia.commands._shared import _format_token_usage, _format_utc
from hestia.commands.registry import (
    Command,
    CommandContext,
    CommandRegistry,
    command_from_handler,
)

if TYPE_CHECKING:
    from hestia.app import AppContext
    from hestia.core.types import Session
    from hestia.persistence.message_store import MessageStore
    from hestia.persistence.session_store import SessionStore


async def _cmd_quit(ctx: CommandContext) -> tuple[bool, Session]:
    """Exit the REPL."""
    return True, ctx.session


async def _cmd_session(ctx: CommandContext) -> tuple[bool, Session]:
    """Print the current session metadata."""
    session = ctx.session
    click.echo(f"Session ID: {session.id}")
    click.echo(f"Platform: {session.platform}")
    click.echo(f"Platform User: {session.platform_user}")
    click.echo(f"State: {session.state.value}")
    click.echo(f"Temperature: {session.temperature.value}")
    click.echo(f"Started: {_format_utc(session.started_at)}")
    if session.slot_id is not None:
        click.echo(f"Slot ID: {session.slot_id}")
    if session.slot_saved_path:
        click.echo(f"Slot path: {session.slot_saved_path}")
    app = ctx.app
    if app is not None and app.policy is not None:
        click.echo(f"Context window: {app.policy.ctx_window} tokens")
        click.echo(f"Turn budget: {app.policy.turn_token_budget(session)} tokens")
    return False, session


async def _cmd_history(ctx: CommandContext) -> tuple[bool, Session]:
    """Print the current session message history."""
    message_store = ctx.message_store
    assert message_store is not None
    messages = await message_store.get_messages(ctx.session.id)
    if not messages:
        click.echo("(empty)")
    else:
        for m in messages:
            role = m.role
            content = (m.content or "")[:200]
            click.echo(f"  [{role}] {content}")
    return False, ctx.session


async def _cmd_compact(ctx: CommandContext) -> tuple[bool, Session]:
    """Compact the current session history."""
    app = ctx.app
    if app is None or app.compactor is None:
        click.echo("Compaction is not available right now.")
        return False, ctx.session
    click.echo("Compacting session...")
    outcome = await app.compactor.compact(ctx.session.id, instruction=ctx.instruction)
    click.echo(outcome.message)
    return False, ctx.session


async def _cmd_reset(ctx: CommandContext) -> tuple[bool, Session]:
    """Start a new session."""
    session = ctx.session
    new_session = await ctx.session_store.create_session(
        platform=session.platform,
        platform_user=session.platform_user,
        archive_previous=session,
    )
    click.echo(f"New session: {new_session.id}")
    # Refresh memory epoch for new session
    app = ctx.app
    if app is not None:
        from hestia.persistence.memory_epochs import _compile_and_set_memory_epoch

        compiled = await _compile_and_set_memory_epoch(app, new_session)
        if compiled:
            click.echo("Memory epoch refreshed.")
    return False, new_session


async def _cmd_refresh(ctx: CommandContext) -> tuple[bool, Session]:
    """Refresh the memory epoch."""
    app = ctx.app
    if app is not None:
        from hestia.persistence.memory_epochs import _compile_and_set_memory_epoch

        compiled = await _compile_and_set_memory_epoch(app, ctx.session)
        if compiled:
            click.echo("Memory epoch refreshed.")
        else:
            click.echo("No memories to include in epoch.")
    else:
        click.echo("Cannot refresh: app context not available.")
    return False, ctx.session


async def _cmd_tokens(ctx: CommandContext) -> tuple[bool, Session]:
    """Show token usage for the most recent turn."""
    app = ctx.app
    if app is None:
        click.echo("Cannot show tokens: app context not available.")
        return False, ctx.session
    if app.trace_store is None:
        click.echo("Trace store not available.")
        return False, ctx.session
    traces = await app.trace_store.list_recent(session_id=ctx.session.id, limit=1)
    if not traces:
        click.echo("No token usage recorded for this session yet.")
        return False, ctx.session
    usage = _format_token_usage(traces[0])
    if usage is None:
        click.echo("No token usage recorded for this session yet.")
    else:
        click.echo(usage)
    return False, ctx.session


def _command_display(command: Command) -> str:
    """Return the command name followed by its aliases."""
    if command.aliases:
        return f"{command.name}, {', '.join(command.aliases)}"
    return command.name


def render_commands_reference(registry: CommandRegistry) -> str:
    """Render the registry catalog as formatted help text.

    Groups by category when any command has a category; otherwise lists
    commands alphabetically. Each line shows the canonical name, aliases,
    and one-line summary.
    """
    commands = registry.commands()
    if not commands:
        return "No commands available."

    displays = [_command_display(command) for command in commands]
    width = max(len(display) for display in displays) + 4 if displays else 0

    lines: list[str] = ["Available commands:", ""]
    has_category = any(command.category is not None for command in commands)

    if has_category:
        by_category: dict[str, list[Command]] = {}
        for command in commands:
            category = command.category or "Other"
            by_category.setdefault(category, []).append(command)
        for category in sorted(by_category):
            lines.append(f"{category}:")
            for command in sorted(by_category[category], key=lambda c: c.name):
                lines.append(
                    f"  {_command_display(command):<{width}} {command.summary}"
                )
            lines.append("")
    else:
        for command in sorted(commands, key=lambda c: c.name):
            lines.append(f"  {_command_display(command):<{width}} {command.summary}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


async def _cmd_commands(ctx: CommandContext) -> tuple[bool, Session]:
    """Show available commands and their descriptions."""
    click.echo(render_commands_reference(_default_registry))
    return False, ctx.session


def _build_default_registry() -> CommandRegistry:
    """Create the registry populated with CLI REPL meta-commands."""
    reg = CommandRegistry()
    reg.register(command_from_handler(name="/quit", handler=_cmd_quit, aliases=("/exit",), category="session"))
    reg.register(command_from_handler(name="/reset", handler=_cmd_reset, category="session"))
    reg.register(command_from_handler(name="/compact", handler=_cmd_compact, category="session"))
    reg.register(command_from_handler(name="/history", handler=_cmd_history, category="session"))
    reg.register(command_from_handler(name="/session", handler=_cmd_session, category="session"))
    reg.register(command_from_handler(name="/refresh", handler=_cmd_refresh, category="memory"))
    reg.register(command_from_handler(name="/tokens", handler=_cmd_tokens, category="session"))
    reg.register(
        command_from_handler(
            name="/commands",
            handler=_cmd_commands,
            aliases=("/help",),
            category="meta",
        )
    )
    return reg


_default_registry = _build_default_registry()


async def _handle_meta_command(
    cmd: str,
    session: Session,
    session_store: SessionStore,
    message_store: MessageStore | None = None,
    app: AppContext | None = None,
) -> tuple[bool, Session]:
    """Handle a /meta command. Returns (should_exit, possibly_new_session).

    This function is preserved as a thin compatibility wrapper around the
    command registry so existing callers (CLI REPL, tests, app re-exports)
    continue to work without changes.
    """
    return await _default_registry.handle(cmd, session, session_store, message_store, app)


# Public entry points for platform adapters and external callers.

def get_meta_command_registry() -> CommandRegistry:
    """Return the default CLI REPL meta-command registry."""
    return _default_registry


# Cross-platform alias used by platform adapters.
get_default_registry = get_meta_command_registry
