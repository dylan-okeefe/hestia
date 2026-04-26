"""Admin, doctor, config, and utility command implementations."""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import click
import httpx

from hestia.app import CliAppContext, _require_scheduler_store
from hestia.core.clock import utcnow
from hestia.errors import HestiaError

from ._shared import _format_utc, _parse_since

logger = logging.getLogger(__name__)


_STARTER_CONFIG = '''\
from pathlib import Path
from hestia.config import (
    HestiaConfig,
    InferenceConfig,
    SlotConfig,
    StorageConfig,
    TelegramConfig,
    TrustConfig,
)

config = HestiaConfig(
    inference=InferenceConfig(
        base_url="http://localhost:8001",
        model_name="your-model-Q4_K_M.gguf",
    ),
    slots=SlotConfig(
        slot_dir=Path("slots"),
        pool_size=4,
    ),
    storage=StorageConfig(
        database_url="sqlite+aiosqlite:///hestia.db",
        artifacts_dir=Path("artifacts"),
        allowed_roots=["."],
    ),
    telegram=TelegramConfig(
        bot_token="YOUR_TOKEN_HERE",
        allowed_users=["YOUR_USER_ID"],
    ),
    trust=TrustConfig.household(),
)
'''

_SOUL_TEMPLATE = '''\
# Hestia Personality

You are Hestia, a calm and capable personal assistant. You help your operator
with daily tasks, coding, research, and creative work.

## Tone

- Warm but concise. Prefer short, actionable responses.
- Use first person ("I") when speaking about yourself.
- Avoid excessive apologies or filler phrases.

## Values

- Clarity over cleverness.
- Respect the operator's time.
- When uncertain, say so rather than hallucinating.

## Anti-patterns

- Don't ask "How can I help you?" more than once per session.
- Don't over-explain simple operations.
- Don't offer to "look that up" unless you actually have a tool for it.

## Context

- Operator name: (edit me)
- Preferred language: English
- Timezone: (edit me, e.g. America/New_York)
'''


async def cmd_init(
    app: CliAppContext, create_config: bool = False, with_soul: bool = False
) -> None:
    """Initialize database, artifacts, and slot directories."""
    cfg = app.config
    cfg.storage.artifacts_dir.mkdir(parents=True, exist_ok=True)
    cfg.slots.slot_dir.mkdir(parents=True, exist_ok=True)
    click.echo(f"Initialized database at {cfg.storage.database_url}")
    click.echo(f"Initialized artifacts directory at {cfg.storage.artifacts_dir}")
    click.echo(f"Initialized slot directory at {cfg.slots.slot_dir}")

    if create_config:
        config_path = Path("config.py")
        if config_path.exists():
            click.echo("config.py already exists — skipping.")
        else:
            config_path.write_text(_STARTER_CONFIG, encoding="utf-8")
            click.echo("Created starter config.py")

    if with_soul:
        soul_path = Path("SOUL.md")
        if soul_path.exists():
            click.echo("SOUL.md already exists — skipping.")
        else:
            soul_path.write_text(_SOUL_TEMPLATE, encoding="utf-8")
            click.echo("Created starter SOUL.md")


async def cmd_artifacts_list(app: CliAppContext) -> list[Any]:
    """Return a list of artifact metadata."""
    return app.artifact_store.list()


async def cmd_artifacts_purge(app: CliAppContext, older_than_days: int | None = None) -> int:
    """Purge artifacts, optionally filtering by age.

    If older_than_days is None, only expired artifacts are removed (GC).
    If set, all artifacts older than that many days are removed.
    """
    if older_than_days is None:
        return app.artifact_store.gc()

    cutoff = datetime.now(UTC).timestamp() - (older_than_days * 24 * 60 * 60)
    removed = 0
    for meta in app.artifact_store.list():
        if meta.created_at < cutoff and app.artifact_store.delete(meta.handle):
            removed += 1

    return removed


async def cmd_health(app: CliAppContext) -> None:
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


async def cmd_status(app: CliAppContext) -> None:
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
        click.echo(f"  Next due: {_format_utc(next_run)}")
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


async def cmd_failures_list(app: CliAppContext, limit: int, failure_class: str | None) -> None:
    """List recent failures."""
    bundles = await app.failure_store.list_recent(limit=limit, failure_class=failure_class)
    if not bundles:
        click.echo("No failures found.")
        return
    for bundle in bundles:
        click.echo(f"\nID: {bundle.id}")
        click.echo(f"  Time: {_format_utc(bundle.created_at)}")
        click.echo(f"  Class: {bundle.failure_class} (severity: {bundle.severity})")
        click.echo(f"  Session: {bundle.session_id}")
        click.echo(f"  Turn: {bundle.turn_id}")
        click.echo(f"  Message: {bundle.error_message[:100]}")
        if len(bundle.error_message) > 100:
            click.echo("  ...")


async def cmd_failures_summary(app: CliAppContext, days: int) -> None:
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


async def cmd_audit_run(app: CliAppContext, output_json: bool, output: str | None) -> None:
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


async def cmd_audit_egress(app: CliAppContext, since: str) -> None:
    """Print domain-level egress aggregation."""
    since_dt = _parse_since(since)
    rows = await app.trace_store.egress_summary(since=since_dt)
    if not rows:
        click.echo("No egress events found in the given window.")
        return
    click.echo(f"Egress summary since {_format_utc(since_dt)}\n")
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


async def cmd_email_check(app: CliAppContext) -> None:
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


async def cmd_email_list_cmd(
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


async def cmd_email_read_cmd(app: CliAppContext, message_id: str) -> None:
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


async def cmd_doctor(app: CliAppContext, plain: bool) -> int:
    """Run health checks. Returns exit code (0 if all green, 1 if any fail)."""
    from hestia.doctor import run_checks, render_results  # noqa: I001

    results = await run_checks(app)
    click.echo(render_results(results, plain=plain))
    return 0 if all(r.ok for r in results) else 1
