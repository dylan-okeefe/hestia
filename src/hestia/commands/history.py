"""History command for retrieving past conversations."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from hestia.app import AppContext


async def cmd_history_list(app: AppContext, limit: int, output_json: bool) -> None:
    """List recent sessions."""
    session_list = await app.session_store.list_sessions(limit=limit)

    if output_json:
        data = [
            {
                "id": s.id,
                "platform": s.platform,
                "platform_user": s.platform_user,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "last_active_at": s.last_active_at.isoformat() if s.last_active_at else None,
                "state": s.state.value,
            }
            for s in session_list
        ]
        click.echo(json.dumps(data, indent=2))
        return

    if not session_list:
        click.echo("No sessions found.")
        return

    click.echo(f"{'ID':<30} {'Platform':<12} {'User':<20} {'Last Active':<25} {'State'}")
    click.echo("-" * 95)
    for s in session_list:
        last_active = (
            s.last_active_at.strftime("%Y-%m-%d %H:%M:%S")
            if s.last_active_at
            else "N/A"
        )
        click.echo(
            f"{s.id:<30} {s.platform:<12} {s.platform_user:<20} {last_active:<25} {s.state.value}"
        )


async def cmd_history_show(
    app: AppContext, session_id: str, output_json: bool
) -> None:
    """Show conversation for a specific session."""
    session = await app.session_store.get_session(session_id)
    if session is None:
        click.echo(click.style(f"Session not found: {session_id}", fg="red"), err=True)
        return

    messages = await app.session_store.get_messages(session_id)

    if output_json:
        data = {
            "session": {
                "id": session.id,
                "platform": session.platform,
                "platform_user": session.platform_user,
                "started_at": session.started_at.isoformat() if session.started_at else None,
                "state": session.state.value,
            },
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "tool_call_id": m.tool_call_id,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in messages
            ],
        }
        click.echo(json.dumps(data, indent=2))
        return

    click.echo(
        f"Session: {session.id} | Platform: {session.platform} | User: {session.platform_user}"
    )
    click.echo("=" * 60)

    for msg in messages:
        role_label = msg.role.capitalize()
        if msg.role == "assistant":
            prefix = click.style(f"{role_label}:", fg="green", bold=True)
        elif msg.role == "user":
            prefix = click.style(f"{role_label}:", fg="blue", bold=True)
        elif msg.role == "tool":
            prefix = click.style(f"{role_label} ({msg.tool_call_id or 'n/a'}):", fg="yellow")
        else:
            prefix = click.style(f"{role_label}:", fg="white")
        click.echo(f"\n{prefix}")
        click.echo(msg.content or "")
