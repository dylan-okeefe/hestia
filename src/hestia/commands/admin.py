"""Admin, doctor, config, and utility command implementations."""

from __future__ import annotations

import logging
import sys
from datetime import UTC, timedelta
from pathlib import Path

import click
import httpx

from hestia.app import CliAppContext, _require_scheduler_store
from hestia.core.clock import utcnow
from hestia.errors import HestiaError

from ._shared import _parse_since

logger = logging.getLogger(__name__)


async def _cmd_init(app: CliAppContext) -> None:
    """Initialize database, artifacts, and slot directories."""
    cfg = app.config
    cfg.storage.artifacts_dir.mkdir(parents=True, exist_ok=True)
    cfg.slots.slot_dir.mkdir(parents=True, exist_ok=True)
    click.echo(f"Initialized database at {cfg.storage.database_url}")
    click.echo(f"Initialized artifacts directory at {cfg.storage.artifacts_dir}")
    click.echo(f"Initialized slot directory at {cfg.slots.slot_dir}")


async def _cmd_health(app: CliAppContext) -> None:
    """Check inference server health."""
    try:
        health_info = await app.inference.health()
        click.echo("Inference server is healthy:")
        for key, value in health_info.items():
            click.echo(f"  {key}: {value}")
    except (HestiaError, httpx.HTTPError, OSError) as e:
        click.echo(f"Health check failed: {e}", err=True)
        sys.exit(1)
    finally:
        await app.inference.close()


async def _cmd_status(app: CliAppContext) -> None:
    """Show system status summary."""
    store = _require_scheduler_store(app)

    # 1. Inference health
    click.echo("Inference:")
    try:
        health_info = await app.inference.health()
        click.echo("  Status: ok")
        for key, value in health_info.items():
            click.echo(f"  {key}: {value}")
    except (HestiaError, httpx.HTTPError, OSError) as e:
        click.echo(f"  Status: failed ({e})")

    # 2. Sessions by state
    click.echo("\nSessions:")
    session_counts = await app.session_store.count_sessions_by_state()
    if session_counts:
        for state, count in sorted(session_counts.items()):
            click.echo(f"  {state}: {count}")
    else:
        click.echo("  No sessions")

    # 3. Turns in last 24h
    click.echo("\nTurns (last 24h):")
    since = utcnow() - timedelta(hours=24)
    turn_stats = await app.session_store.turn_stats_since(since)
    if turn_stats:
        for state, count in sorted(turn_stats.items()):
            click.echo(f"  {state}: {count}")
    else:
        click.echo("  No turns")

    # 4. Scheduled tasks
    click.echo("\nScheduled Tasks:")
    stats = await store.summary_stats()
    click.echo(f"  Enabled: {stats['enabled_count']}")
    if stats["next_run_at"]:
        next_run = stats["next_run_at"]
        if next_run.tzinfo is None:
            next_run = next_run.replace(tzinfo=UTC)
        click.echo(f"  Next due: {next_run.astimezone().strftime('%Y-%m-%d %H:%M %Z')}")
    else:
        click.echo("  Next due: none")

    # 5. Failures in last 24h
    click.echo("\nFailures (last 24h):")
    failure_counts = await app.failure_store.count_by_class(since=since)
    if failure_counts:
        for failure_class, count in sorted(failure_counts.items()):
            click.echo(f"  {failure_class}: {count}")
    else:
        click.echo("  No failures")

    await app.inference.close()


async def _cmd_failures_list(app: CliAppContext, limit: int, failure_class: str | None) -> None:
    """List recent failures."""
    bundles = await app.failure_store.list_recent(limit=limit, failure_class=failure_class)
    if not bundles:
        click.echo("No failures found.")
        return
    for bundle in bundles:
        click.echo(f"\nID: {bundle.id}")
        click.echo(f"  Time: {bundle.created_at}")
        click.echo(f"  Class: {bundle.failure_class} (severity: {bundle.severity})")
        click.echo(f"  Session: {bundle.session_id}")
        click.echo(f"  Turn: {bundle.turn_id}")
        click.echo(f"  Message: {bundle.error_message[:100]}")
        if len(bundle.error_message) > 100:
            click.echo("  ...")


async def _cmd_failures_summary(app: CliAppContext, days: int) -> None:
    """Show failure counts by class."""
    since = utcnow() - timedelta(days=days)
    counts = await app.failure_store.count_by_class(since=since)
    click.echo(f"Failure summary (last {days} days):\n")
    if counts:
        total = sum(counts.values())
        for failure_class, count in sorted(counts.items(), key=lambda x: -x[1]):
            click.echo(f"  {failure_class}: {count}")
        click.echo(f"\nTotal: {total}")
    else:
        click.echo("  No failures in this period.")


async def _cmd_audit_run(app: CliAppContext, output_json: bool, output: str | None) -> None:
    """Run security audit checks."""
    from hestia.audit import SecurityAuditor

    auditor = SecurityAuditor(
        config=app.config,
        tool_registry=app.tool_registry,
        trace_store=app.trace_store,
    )
    report = await auditor.run_audit()
    result = report.to_json() if output_json else report.summary()
    if output:
        Path(output).write_text(result, encoding="utf-8")
        click.echo(f"Audit report saved to: {output}")
    else:
        click.echo(result)
    critical_count = sum(1 for f in report.findings if f.severity == "critical")
    if critical_count > 0:
        sys.exit(1)


async def _cmd_audit_egress(app: CliAppContext, since: str) -> None:
    """Print domain-level egress aggregation."""
    since_dt = _parse_since(since)
    rows = await app.trace_store.egress_summary(since=since_dt)
    if not rows:
        click.echo("No egress events found in the given window.")
        return
    click.echo(f"Egress summary since {since_dt.isoformat()}\n")
    click.echo(f"{'Domain':<40} {'Requests':>10} {'Failures':>10} {'Anomaly'}")
    click.echo("-" * 80)
    for row in rows:
        domain = row["domain"]
        total = row["total_requests"]
        failures = row["failure_count"]
        anomaly = ""
        if total < 3:
            anomaly = "LOW_VOLUME"
        click.echo(f"{domain:<40} {total:>10} {failures:>10} {anomaly}")


async def _cmd_email_check(app: CliAppContext) -> None:
    """Check email connectivity (IMAP login test)."""
    cfg = app.config
    if not cfg.email.imap_host:
        click.echo("Email is not configured. Set email.imap_host in your config.", err=True)
        sys.exit(1)
    from hestia.email.adapter import EmailAdapter

    adapter = EmailAdapter(cfg.email)
    try:
        messages = await adapter.list_messages(limit=1)
    except Exception as exc:
        click.echo(f"Email check failed: {type(exc).__name__}: {exc}", err=True)
        sys.exit(1)
    click.echo(
        f"IMAP connection OK ({cfg.email.imap_host}:{cfg.email.imap_port})"
    )
    click.echo(f"Default folder: {cfg.email.default_folder}")
    click.echo(f"Messages found: {len(messages)}")


async def _cmd_email_list_cmd(
    app: CliAppContext, folder: str, limit: int, unread_only: bool
) -> None:
    """List recent emails."""
    cfg = app.config
    if not cfg.email.imap_host:
        click.echo("Email is not configured.", err=True)
        sys.exit(1)
    from hestia.email.adapter import EmailAdapter

    adapter = EmailAdapter(cfg.email)
    try:
        messages = await adapter.list_messages(folder=folder, limit=limit, unread_only=unread_only)
    except Exception as exc:
        click.echo(f"Failed: {type(exc).__name__}: {exc}", err=True)
        sys.exit(1)
    if not messages:
        click.echo("No messages found.")
        return
    for m in messages:
        click.echo(f"[{m['message_id']}] {m['from']} | {m['subject']} | {m['date']}")


async def _cmd_email_read_cmd(app: CliAppContext, message_id: str) -> None:
    """Read a single email by IMAP UID."""
    cfg = app.config
    if not cfg.email.imap_host:
        click.echo("Email is not configured.", err=True)
        sys.exit(1)
    from hestia.email.adapter import EmailAdapter

    adapter = EmailAdapter(cfg.email)
    try:
        result = await adapter.read_message(message_id)
    except Exception as exc:
        click.echo(f"Failed: {type(exc).__name__}: {exc}", err=True)
        sys.exit(1)
    headers = result["headers"]
    click.echo(f"From: {headers['from']}")
    click.echo(f"To: {headers['to']}")
    click.echo(f"Subject: {headers['subject']}")
    click.echo(f"Date: {headers['date']}")
    click.echo("")
    click.echo(result["body"])
    if result["attachments"]:
        click.echo("")
        click.echo("Attachments:")
        for att in result["attachments"]:
            click.echo(f"  - {att['filename']} ({att['content_type']})")


async def _cmd_doctor(app: CliAppContext, plain: bool) -> int:
    """Run health checks. Returns exit code (0 if all green, 1 if any fail)."""
    from hestia.doctor import run_checks, render_results  # noqa: I001

    results = await run_checks(app)
    click.echo(render_results(results, plain=plain))
    return 0 if all(r.ok for r in results) else 1
