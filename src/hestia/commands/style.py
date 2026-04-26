"""Style-related command implementations."""

from __future__ import annotations

import sys

import click

from hestia.app import AppContext


async def cmd_style_show(app: AppContext, platform: str | None, user: str | None) -> None:
    """Pretty-print the current style profile for a user."""
    if app.style_store is None:
        click.echo("Style store not available", err=True)
        sys.exit(1)
    platform = platform or "cli"
    platform_user = user or "default"
    metrics = await app.style_store.list_metrics(platform, platform_user)
    if not metrics:
        click.echo(f"No style profile found for {platform}/{platform_user}.")
        return
    click.echo(f"Style profile for {platform}/{platform_user}:")
    for m in metrics:
        click.echo(f"  {m.metric}: {m.value_json}")
    if app.style_scheduler is not None:
        sched_status = app.style_scheduler.status()
        if not sched_status["ok"]:
            click.echo("")
            click.echo("Failures:")
            click.echo(f"  Total: {sched_status['failure_count']}")
            for err in sched_status["last_errors"]:
                click.echo(f"  {err['timestamp']} UTC  {err['type']:<20} {err['message']}")
