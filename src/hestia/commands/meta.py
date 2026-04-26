"""Meta-command handler for Hestia CLI REPL."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from hestia.core.types import Session
from hestia.persistence.sessions import SessionStore

if TYPE_CHECKING:
    from hestia.app import CliAppContext
from hestia.commands._shared import _format_token_usage, _format_utc


async def _handle_meta_command(
    cmd: str,
    session: Session,
    session_store: SessionStore,
    app: CliAppContext | None = None,
) -> tuple[bool, Session]:
    """Handle a /meta command. Returns (should_exit, possibly_new_session)."""
    cmd = cmd.strip().lower()

    if cmd in ("/quit", "/exit"):
        return True, session

    if cmd == "/help":
        click.echo("Meta-commands:")
        click.echo("  /quit, /exit     Exit the REPL")
        click.echo("  /reset           Start a new session")
        click.echo("  /history         Print the current session message history")
        click.echo("  /session         Print the current session metadata")
        click.echo("  /refresh         Refresh the memory epoch")
        click.echo("  /tokens          Show token usage for the most recent turn")
        click.echo("  /help            Show this help")
        return False, session

    if cmd == "/session":
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

    if cmd == "/history":
        messages = await session_store.get_messages(session.id)
        if not messages:
            click.echo("(empty)")
        else:
            for m in messages:
                role = m.role
                content = (m.content or "")[:200]
                click.echo(f"  [{role}] {content}")
        return False, session

    if cmd == "/reset":
        new_session = await session_store.create_session(
            platform=session.platform,
            platform_user=session.platform_user,
            archive_previous=session,
        )
        click.echo(f"New session: {new_session.id}")
        # Refresh memory epoch for new session
        if app is not None:
            from hestia.app import _compile_and_set_memory_epoch

            compiled = await _compile_and_set_memory_epoch(app, new_session)
            if compiled:
                click.echo("Memory epoch refreshed.")
        return False, new_session

    if cmd == "/refresh":
        if app is not None:
            from hestia.app import _compile_and_set_memory_epoch

            compiled = await _compile_and_set_memory_epoch(app, session)
            if compiled:
                click.echo("Memory epoch refreshed.")
            else:
                click.echo("No memories to include in epoch.")
        else:
            click.echo("Cannot refresh: app context not available.")
        return False, session

    if cmd == "/tokens":
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

    click.echo(f"Unknown command: {cmd}. Type /help for a list.")
    return False, session
