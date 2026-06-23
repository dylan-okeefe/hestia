"""Meta-command handler for Hestia CLI REPL."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from hestia.core.types import Session
from hestia.persistence.message_store import MessageStore
from hestia.persistence.session_store import SessionStore

if TYPE_CHECKING:
    from hestia.app import AppContext
from hestia.commands._shared import _format_token_usage, _format_utc


def _parse_meta_command(cmd: str) -> tuple[str, str | None]:
    """Split a /command from its optional trailing instruction.

    Examples:
      "/compact" -> ("/compact", None)
      "/compact keep the job criteria" -> ("/compact", "keep the job criteria")
    """
    stripped = cmd.strip()
    parts = stripped.split(None, 1)
    base = parts[0].lower() if parts else ""
    instruction = parts[1] if len(parts) > 1 else None
    return base, instruction


async def _handle_meta_command(
    cmd: str,
    session: Session,
    session_store: SessionStore,
    message_store: MessageStore | None = None,
    app: AppContext | None = None,
) -> tuple[bool, Session]:
    """Handle a /meta command. Returns (should_exit, possibly_new_session)."""
    base, instruction = _parse_meta_command(cmd)

    if base in ("/quit", "/exit"):
        return True, session

    if base == "/help":
        click.echo("Meta-commands:")
        click.echo("  /quit, /exit     Exit the REPL")
        click.echo("  /reset           Start a new session")
        click.echo("  /compact         Compact the current session history")
        click.echo("  /history         Print the current session message history")
        click.echo("  /session         Print the current session metadata")
        click.echo("  /refresh         Refresh the memory epoch")
        click.echo("  /tokens          Show token usage for the most recent turn")
        click.echo("  /help            Show this help")
        return False, session

    if base == "/session":
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
        if app is not None and app.policy is not None:
            click.echo(f"Context window: {app.policy.ctx_window} tokens")
            click.echo(f"Turn budget: {app.policy.turn_token_budget(session)} tokens")
        return False, session

    if base == "/history":
        assert message_store is not None
        messages = await message_store.get_messages(session.id)
        if not messages:
            click.echo("(empty)")
        else:
            for m in messages:
                role = m.role
                content = (m.content or "")[:200]
                click.echo(f"  [{role}] {content}")
        return False, session

    if base == "/compact":
        if app is None or app.compactor is None:
            click.echo("Compaction is not available right now.")
            return False, session
        click.echo("Compacting session...")
        outcome = await app.compactor.compact(session.id, instruction=instruction)
        click.echo(outcome.message)
        return False, session

    if base == "/reset":
        new_session = await session_store.create_session(
            platform=session.platform,
            platform_user=session.platform_user,
            archive_previous=session,
        )
        click.echo(f"New session: {new_session.id}")
        # Refresh memory epoch for new session
        if app is not None:
            from hestia.persistence.memory_epochs import _compile_and_set_memory_epoch

            compiled = await _compile_and_set_memory_epoch(app, new_session)
            if compiled:
                click.echo("Memory epoch refreshed.")
        return False, new_session

    if base == "/refresh":
        if app is not None:
            from hestia.persistence.memory_epochs import _compile_and_set_memory_epoch

            compiled = await _compile_and_set_memory_epoch(app, session)
            if compiled:
                click.echo("Memory epoch refreshed.")
            else:
                click.echo("No memories to include in epoch.")
        else:
            click.echo("Cannot refresh: app context not available.")
        return False, session

    if base == "/tokens":
        if app is None:
            click.echo("Cannot show tokens: app context not available.")
            return False, session
        if app.trace_store is None:
            click.echo("Trace store not available.")
            return False, session
        traces = await app.trace_store.list_recent(session_id=session.id, limit=1)
        if not traces:
            click.echo("No token usage recorded for this session yet.")
            return False, session
        usage = _format_token_usage(traces[0])
        if usage is None:
            click.echo("No token usage recorded for this session yet.")
        else:
            click.echo(usage)
        return False, session

    click.echo(f"Unknown command: {base}. Type /help for a list.")
    return False, session
