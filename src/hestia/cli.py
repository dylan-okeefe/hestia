"""CLI adapter for Hestia - local-first LLM agent framework."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

import click

from hestia.app import (
    CliAppContext,
    async_command,
    make_app,
)
from hestia.commands import (
    cmd_ask,
    cmd_audit_egress,
    cmd_audit_run,
    cmd_chat,
    cmd_doctor,
    cmd_email_check,
    cmd_email_list_cmd,
    cmd_email_read_cmd,
    cmd_failures_list,
    cmd_failures_summary,
    cmd_health,
    cmd_init,
    cmd_policy_show,
    cmd_reflection_accept,
    cmd_reflection_defer,
    cmd_reflection_history,
    cmd_reflection_list,
    cmd_reflection_reject,
    cmd_reflection_run,
    cmd_reflection_show,
    cmd_reflection_status,
    cmd_schedule_add,
    cmd_schedule_daemon,
    cmd_schedule_disable,
    cmd_schedule_enable,
    cmd_schedule_list,
    cmd_schedule_remove,
    cmd_schedule_run,
    cmd_schedule_show,
    cmd_skill_demote,
    cmd_skill_disable,
    cmd_skill_list,
    cmd_skill_promote,
    cmd_skill_show,
    cmd_status,
    cmd_style_show,
)
from hestia.config import HestiaConfig
from hestia.logging_config import setup_logging

logger = logging.getLogger(__name__)

@click.group()
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True),
    default=None,
    help="Path to Hestia config file (Python)",
)
@click.option("--db-path", type=click.Path(), default=None)
@click.option("--artifacts-path", type=click.Path(), default=None)
@click.option("--slot-dir", type=click.Path(), default=None)
@click.option("--slot-pool-size", type=int, default=None)
@click.option("--inference-url", default=None)
@click.option("--model", default=None)
@click.option("--verbose", "-v", is_flag=True, default=False)
@click.pass_context
def cli(
    ctx: click.Context,
    config_path: str | None,
    db_path: str | None,
    artifacts_path: str | None,
    slot_dir: str | None,
    slot_pool_size: int | None,
    inference_url: str | None,
    model: str | None,
    verbose: bool,
) -> None:
    """Hestia - Local-first LLM agent framework."""
    ctx.ensure_object(dict)

    # Load config
    cfg = (
        HestiaConfig.from_file(Path(config_path))
        if config_path
        else HestiaConfig.default()
    )

    # Apply CLI overrides (only when explicitly provided)
    if db_path is not None:
        cfg.storage.database_url = f"sqlite+aiosqlite:///{db_path}"
    if artifacts_path is not None:
        cfg.storage.artifacts_dir = Path(artifacts_path)
    if slot_dir is not None:
        cfg.slots.slot_dir = Path(slot_dir)
    if slot_pool_size is not None:
        cfg.slots.pool_size = slot_pool_size
    if inference_url is not None:
        cfg.inference.base_url = inference_url
    if model is not None:
        cfg.inference.model_name = model
    if verbose:
        cfg.verbose = True

    # Setup logging after config is finalized
    setup_logging(cfg.verbose)

    # Build typed app context (lazy inference — no httpx client spun up yet)
    ctx.obj = make_app(cfg)

@cli.command()
@click.option("--create-config", is_flag=True, help="Write a starter config.py")
@click.option("--with-soul", is_flag=True, help="Write a starter SOUL.md")
@click.pass_obj
@async_command
async def init(app: CliAppContext, create_config: bool, with_soul: bool) -> None:
    """Initialize database, artifacts, and slot directories."""
    await cmd_init(app, create_config, with_soul)

@cli.command()
@click.option("--new-session", is_flag=True, help="Force a new session instead of resuming")
@click.pass_obj
@async_command
async def chat(app: CliAppContext, new_session: bool) -> None:
    """Start an interactive chat session."""
    await cmd_chat(app, new_session)

@cli.command()
@click.argument("message")
@click.pass_obj
@async_command
async def ask(app: CliAppContext, message: str) -> None:
    """Send a single message and get a response."""
    await cmd_ask(app, message)

@cli.command()
@click.pass_obj
@async_command
async def health(app: CliAppContext) -> None:
    """Check inference server health."""
    await cmd_health(app)

@cli.command()
def version() -> None:
    """Show Hestia version."""
    from importlib.metadata import version as get_version

    click.echo(f"Hestia {get_version('hestia')}")
    click.echo(f"Python {sys.version}")

@cli.command()
@click.pass_obj
@async_command
async def status(app: CliAppContext) -> None:
    """Show system status summary."""
    await cmd_status(app)

# Failures command group
@cli.group()
def failures() -> None:
    """View failure history."""
    pass

@failures.command(name="list")
@click.option("--limit", type=int, default=20, help="Maximum number of failures to show")
@click.option("--class", "failure_class", default=None, help="Filter by failure class")
@click.pass_obj
@async_command
async def failures_list(app: CliAppContext, limit: int, failure_class: str | None) -> None:
    """List recent failures."""
    await cmd_failures_list(app, limit, failure_class)

@failures.command(name="summary")
@click.option("--days", type=int, default=7, help="Number of days to summarize")
@click.pass_obj
@async_command
async def failures_summary(app: CliAppContext, days: int) -> None:
    """Show failure counts by class."""
    await cmd_failures_summary(app, days)

# Schedule command group
@cli.group()
def schedule() -> None:
    """Manage scheduled tasks."""
    pass

@schedule.command(name="add")
@click.option("--cron", help="Cron expression (e.g., '0 9 * * 1-5' for weekdays at 9am)")
@click.option("--at", "fire_at_str", help="One-shot time (ISO format: 2026-04-15T15:00:00)")
@click.option("--description", "-d", help="Task description")
@click.option("--session-id", help="Bind task to an existing session ID")
@click.option("--platform", help="Platform for session binding (e.g., matrix)")
@click.option("--platform-user", help="Platform user for session binding (e.g., room ID)")
@click.option("--notify", is_flag=True, help="Push task output to the session's platform")
@click.argument("prompt")
@click.pass_obj
@async_command
async def schedule_add(
    app: CliAppContext,
    cron: str | None,
    fire_at_str: str | None,
    description: str | None,
    session_id: str | None,
    platform: str | None,
    platform_user: str | None,
    notify: bool,
    prompt: str,
) -> None:
    await cmd_schedule_add(
        app, cron, fire_at_str, description, session_id, platform, platform_user, notify, prompt
    )

@schedule.command(name="list")
@click.pass_obj
@async_command
async def schedule_list(app: CliAppContext) -> None:
    """List scheduled tasks."""
    await cmd_schedule_list(app)

@schedule.command(name="show")
@click.argument("task_id")
@click.pass_obj
@async_command
async def schedule_show(app: CliAppContext, task_id: str) -> None:
    """Show details of a scheduled task."""
    await cmd_schedule_show(app, task_id)

@schedule.command(name="disable")
@click.argument("task_id")
@click.pass_obj
@async_command
async def schedule_disable(app: CliAppContext, task_id: str) -> None:
    """Disable a scheduled task."""
    await cmd_schedule_disable(app, task_id)

@schedule.command(name="remove")
@click.argument("task_id")
@click.pass_obj
@async_command
async def schedule_remove(app: CliAppContext, task_id: str) -> None:
    """Remove a scheduled task."""
    await cmd_schedule_remove(app, task_id)

@schedule.command(name="enable")
@click.argument("task_id")
@click.pass_obj
@async_command
async def schedule_enable(app: CliAppContext, task_id: str) -> None:
    """Enable a scheduled task."""
    await cmd_schedule_enable(app, task_id)

@schedule.command(name="run")
@click.argument("task_id")
@click.pass_obj
@async_command
async def schedule_run(app: CliAppContext, task_id: str) -> None:
    """Manually trigger a scheduled task."""
    await cmd_schedule_run(app, task_id)

@schedule.command(name="daemon")
@click.option(
    "--tick-interval",
    type=float,
    default=None,
    help="Tick interval in seconds (default: from config)",
)
@click.pass_context
def schedule_daemon(ctx: click.Context, tick_interval: float | None) -> None:
    """Run the scheduler daemon (blocks until Ctrl-C)."""
    cmd_schedule_daemon(ctx, tick_interval)

@cli.command(name="telegram")
@click.pass_context
def run_telegram(ctx: click.Context) -> None:
    """Run Hestia as a Telegram bot (blocks until Ctrl-C)."""
    app: CliAppContext = ctx.obj
    from hestia.platforms.runners import run_telegram as _run_telegram

    try:
        asyncio.run(_run_telegram(app, app.config))
    except KeyboardInterrupt:
        click.echo("\nShutting down.")

@cli.command(name="matrix")
@click.pass_context
def run_matrix(ctx: click.Context) -> None:
    """Run Hestia as a Matrix bot (blocks until Ctrl-C)."""
    app: CliAppContext = ctx.obj
    from hestia.platforms.runners import run_matrix as _run_matrix

    try:
        asyncio.run(_run_matrix(app, app.config))
    except KeyboardInterrupt:
        click.echo("\nShutting down.")


# Memory command group
@cli.group()
def memory() -> None:
    """Manage long-term memory."""
    pass

def _format_memory_row(mem: Any, id_width: int = 20) -> str:
    tags_str = ", ".join(mem.tags) if mem.tags else ""
    tags = f"[{tags_str}]" if tags_str else ""
    date = mem.created_at.strftime("%Y-%m-%d %H:%M")
    content = mem.content.replace("\n", " ")
    if len(content) > 60:
        content = content[:57] + "..."
    return f"{mem.id:<{id_width}} {date} {tags:<20} {content}"


@memory.command(name="search")
@click.argument("query")
@click.option("--limit", type=int, default=5)
@click.pass_obj
@async_command
async def memory_search(app: CliAppContext, query: str, limit: int) -> None:
    """Search memories."""
    results = await app.memory_store.search(query, limit=limit)
    if not results:
        click.echo("No memories found.")
        return
    click.echo(f"{'ID':<20} {'Date':<16} {'Tags':<20} Content")
    click.echo("-" * 80)
    for mem in results:
        click.echo(_format_memory_row(mem))

@memory.command(name="list")
@click.option("--tag", default=None)
@click.option("--limit", type=int, default=20)
@click.pass_obj
@async_command
async def memory_list(app: CliAppContext, tag: str | None, limit: int) -> None:
    """List recent memories."""
    results = await app.memory_store.list_memories(tag=tag, limit=limit)
    if not results:
        click.echo("No memories found.")
        return
    click.echo(f"{'ID':<20} {'Date':<16} {'Tags':<20} Content")
    click.echo("-" * 80)
    for mem in results:
        click.echo(_format_memory_row(mem))

@memory.command(name="add")
@click.argument("content")
@click.option("--tags", default="")
@click.pass_obj
@async_command
async def memory_add(app: CliAppContext, content: str, tags: str) -> None:
    """Add a memory manually."""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    mem = await app.memory_store.save(content=content, tags=tag_list)
    click.echo(f"Saved: {mem.id}")

@memory.command(name="remove")
@click.argument("memory_id")
@click.pass_obj
@async_command
async def memory_remove(app: CliAppContext, memory_id: str) -> None:
    """Delete a memory by ID."""
    success = await app.memory_store.delete(memory_id)
    if not success:
        click.echo(f"Memory not found: {memory_id}", err=True)
        sys.exit(1)
    click.echo(f"Deleted: {memory_id}")

# Skill command group
@cli.group()
def skill() -> None:
    """Manage skills."""
    pass


_EXPERIMENTAL_SKILLS_MESSAGE = (
    "Skills are an experimental preview. Set HESTIA_EXPERIMENTAL_SKILLS=1 to opt in. "
    "See README.md#skills."
)


def _check_experimental_skills() -> None:
    import os

    if os.environ.get("HESTIA_EXPERIMENTAL_SKILLS") != "1":
        click.echo(_EXPERIMENTAL_SKILLS_MESSAGE, err=True)
        sys.exit(1)


@skill.command(name="list")
@click.option(
    "--state",
    "state_filter",
    default=None,
    help="Filter by state (draft, tested, trusted, deprecated, disabled)",
)
@click.option("--all", "show_all", is_flag=True, help="Include disabled skills")
@click.pass_obj
@async_command
async def skill_list(app: CliAppContext, state_filter: str | None, show_all: bool) -> None:
    """List skills with their states."""
    _check_experimental_skills()
    await cmd_skill_list(app, state_filter, show_all)

@skill.command(name="show")
@click.argument("name")
@click.pass_obj
@async_command
async def skill_show(app: CliAppContext, name: str) -> None:
    """Show skill details."""
    _check_experimental_skills()
    await cmd_skill_show(app, name)

@skill.command(name="promote")
@click.argument("name")
@click.pass_obj
@async_command
async def skill_promote(app: CliAppContext, name: str) -> None:
    """Advance skill state (draft -> tested -> trusted)."""
    _check_experimental_skills()
    await cmd_skill_promote(app, name)

@skill.command(name="demote")
@click.argument("name")
@click.pass_obj
@async_command
async def skill_demote(app: CliAppContext, name: str) -> None:
    """Move skill back one state."""
    _check_experimental_skills()
    await cmd_skill_demote(app, name)

@skill.command(name="disable")
@click.argument("name")
@click.pass_obj
@async_command
async def skill_disable(app: CliAppContext, name: str) -> None:
    """Disable a skill without removing it."""
    _check_experimental_skills()
    await cmd_skill_disable(app, name)

class AuditGroup(click.Group):
    """Custom group that defaults to 'run' when no subcommand is given."""

    def invoke(self, ctx: click.Context) -> Any:
        if ctx.invoked_subcommand is None:
            ctx.invoked_subcommand = "run"
        return super().invoke(ctx)

@cli.group(name="audit", cls=AuditGroup, invoke_without_command=True)
def audit_group() -> None:
    """Security audit commands."""
    pass

@audit_group.command(name="run")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--output", "-o", type=click.Path(), help="Save report to file")
@click.pass_obj
@async_command
async def audit_run(app: CliAppContext, output_json: bool, output: str | None) -> None:
    """Run security audit checks."""
    await cmd_audit_run(app, output_json, output)

@audit_group.command(name="egress")
@click.option("--since", default="7d", help="Time window (e.g. 7d, 24h, 30d)")
@click.pass_obj
@async_command
async def audit_egress(app: CliAppContext, since: str) -> None:
    """Print domain-level egress aggregation."""
    await cmd_audit_egress(app, since)

# Email CLI
@cli.group()
def email() -> None:
    """Email integration commands."""
    pass

@email.command(name="check")
@click.pass_obj
@async_command
async def email_check(app: CliAppContext) -> None:
    """Check email connectivity (IMAP login test)."""
    await cmd_email_check(app)

@email.command(name="list")
@click.option("--folder", default="INBOX", help="IMAP folder")
@click.option("--limit", default=5, help="Max messages")
@click.option("--unread-only", is_flag=True, default=False)
@click.pass_obj
@async_command
async def email_list_cmd(app: CliAppContext, folder: str, limit: int, unread_only: bool) -> None:
    """List recent emails."""
    await cmd_email_list_cmd(app, folder, limit, unread_only)

@email.command(name="read")
@click.argument("message_id")
@click.pass_obj
@async_command
async def email_read_cmd(app: CliAppContext, message_id: str) -> None:
    """Read a single email by IMAP UID."""
    await cmd_email_read_cmd(app, message_id)

@cli.group()
def style() -> None:
    """Manage interaction-style profile."""
    pass

@style.command(name="show")
@click.option("--platform", default=None)
@click.option("--user", default=None)
@click.pass_obj
@async_command
async def style_show(app: CliAppContext, platform: str | None, user: str | None) -> None:
    """Pretty-print the current style profile for a user."""
    await cmd_style_show(app, platform, user)

@style.command(name="reset")
@click.option("--platform", default=None)
@click.option("--user", default=None)
@click.pass_obj
@async_command
async def style_reset(app: CliAppContext, platform: str | None, user: str | None) -> None:
    """Wipe the style profile so it rebuilds from scratch."""
    if app.style_store is None:
        click.echo("Style store not available", err=True)
        sys.exit(1)
    platform = platform or "cli"
    platform_user = user or "default"
    count = await app.style_store.delete_profile(platform, platform_user)
    click.echo(f"Deleted {count} metric(s) for {platform}/{platform_user}.")

@style.command(name="disable")
@click.pass_obj
def style_disable(app: CliAppContext) -> None:
    """Disable style profile injection for this process only.

    To disable persistently, set ``style.enabled = false`` in your config
    file, or export ``HESTIA_STYLE_ENABLED=0`` before starting Hestia.
    """
    app.config.style.enabled = False
    click.echo(
        "Style profile disabled for this process. "
        "Set style.enabled=false in config to make this permanent."
    )

@cli.group()
def policy() -> None:
    """Manage and view security policies."""
    pass

@policy.command(name="show")
@click.pass_obj
@async_command
async def policy_show(app: CliAppContext) -> None:
    """Show current effective policy configuration."""
    await cmd_policy_show(app)

@cli.command()
@click.option("--plain", is_flag=True, help="Use ASCII [ok]/[FAIL] markers instead of ✓/✗.")
@click.pass_obj
@async_command
async def doctor(app: CliAppContext, plain: bool) -> None:
    """Run a one-shot health check against the current Hestia install.

    Exits non-zero if any check fails. Read-only; never mutates state.
    Run this first when something seems wrong.
    """
    exit_code = await cmd_doctor(app, plain=plain)
    if exit_code != 0:
        sys.exit(exit_code)

# Reflection commands
@cli.group(name="reflection")
def reflection() -> None:
    """Manage reflection proposals."""
    pass

@reflection.command(name="status")
@click.pass_obj
@async_command
async def reflection_status(app: CliAppContext) -> None:
    """Show reflection scheduler health and proposal counts."""
    await cmd_reflection_status(app)

@reflection.command(name="list")
@click.option("--status", default="pending", help="Filter by status")
@click.pass_obj
@async_command
async def reflection_list(app: CliAppContext, status: str) -> None:
    """List proposals."""
    await cmd_reflection_list(app, status)

@reflection.command(name="show")
@click.argument("proposal_id")
@click.pass_obj
@async_command
async def reflection_show(app: CliAppContext, proposal_id: str) -> None:
    """Show full details of a proposal."""
    await cmd_reflection_show(app, proposal_id)

@reflection.command(name="accept")
@click.argument("proposal_id")
@click.pass_obj
@async_command
async def reflection_accept(app: CliAppContext, proposal_id: str) -> None:
    """Accept a proposal (marks it accepted; does not auto-apply)."""
    await cmd_reflection_accept(app, proposal_id)

@reflection.command(name="reject")
@click.argument("proposal_id")
@click.option("--note", default=None, help="Optional rejection note")
@click.pass_obj
@async_command
async def reflection_reject(app: CliAppContext, proposal_id: str, note: str | None) -> None:
    """Reject a proposal."""
    await cmd_reflection_reject(app, proposal_id, note)

@reflection.command(name="defer")
@click.argument("proposal_id")
@click.option("--until", default=None, help="Defer until ISO datetime (e.g. 2026-05-01T00:00:00)")
@click.pass_obj
@async_command
async def reflection_defer(app: CliAppContext, proposal_id: str, until: str | None) -> None:
    """Defer a proposal."""
    await cmd_reflection_defer(app, proposal_id, until)

@reflection.command(name="run")
@click.option("--now", is_flag=True, help="Trigger reflection immediately")
@click.pass_obj
@async_command
async def reflection_run(app: CliAppContext, now: bool) -> None:
    """Run reflection manually (requires --now)."""
    await cmd_reflection_run(app, now)

@reflection.command(name="history")
@click.pass_obj
@async_command
async def reflection_history(app: CliAppContext) -> None:
    """Show past proposals and their outcomes."""
    await cmd_reflection_history(app)

def main() -> None:
    """Entry point for the CLI."""
    cli()

if __name__ == "__main__":
    main()
