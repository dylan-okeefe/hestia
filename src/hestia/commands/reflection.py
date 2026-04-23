"""Reflection-related command implementations."""

from __future__ import annotations

import sys

import click

from hestia.app import CliAppContext


async def cmd_reflection_status(app: CliAppContext) -> None:
    """Show reflection scheduler health and proposal counts."""
    if app.reflection_scheduler is not None:
        sched_status = app.reflection_scheduler.status()
        ok = "ok" if sched_status["ok"] else "degraded"
        click.echo(f"Scheduler: {ok} ({sched_status['failure_count']} failure(s))")
        if sched_status["last_run_at"]:
            click.echo(f"Last run: {sched_status['last_run_at'].isoformat()}")
        else:
            click.echo("Last run: never")
        if sched_status["last_errors"]:
            click.echo("Last errors:")
            for err in sched_status["last_errors"]:
                click.echo(
                    f"  {err['timestamp']}  {err['stage']:<10} "
                    f"{err['type']:<20} {err['message']}"
                )
    else:
        click.echo("Scheduler: not configured (0 failures)")

    if app.proposal_store is not None:
        click.echo("")
        click.echo("Proposals:")
        counts = await app.proposal_store.count_by_status()
        for status in ("pending", "accepted", "rejected", "deferred", "expired"):
            click.echo(f"  {status}: {counts.get(status, 0)}")
    else:
        click.echo("Proposal store: not configured")


async def cmd_reflection_list(app: CliAppContext, status: str) -> None:
    """List proposals."""
    if app.proposal_store is None:
        click.echo("Proposal store not configured.", err=True)
        sys.exit(1)
    proposals = await app.proposal_store.list_by_status(status=status, limit=100)  # type: ignore[arg-type]
    if not proposals:
        click.echo("No proposals found.")
        return
    click.echo(f"{'ID':<20} {'Type':<18} {'Confidence':<12} {'Summary'}")
    click.echo("-" * 80)
    for p in proposals:
        summary = p.summary[:40] + "..." if len(p.summary) > 40 else p.summary
        click.echo(f"{p.id:<20} {p.type:<18} {p.confidence:<12.2f} {summary}")


async def cmd_reflection_show(app: CliAppContext, proposal_id: str) -> None:
    """Show full details of a proposal."""
    if app.proposal_store is None:
        click.echo("Proposal store not configured.", err=True)
        sys.exit(1)
    p = await app.proposal_store.get(proposal_id)
    if p is None:
        click.echo(f"Proposal not found: {proposal_id}", err=True)
        sys.exit(1)
    click.echo(f"ID:          {p.id}")
    click.echo(f"Type:        {p.type}")
    click.echo(f"Status:      {p.status}")
    click.echo(f"Confidence:  {p.confidence:.2f}")
    click.echo(f"Created:     {p.created_at}")
    click.echo(f"Expires:     {p.expires_at}")
    click.echo(f"Evidence:    {', '.join(p.evidence)}")
    click.echo(f"Summary:     {p.summary}")
    click.echo(f"Action:      {p.action}")
    if p.review_note:
        click.echo(f"Review note: {p.review_note}")


async def cmd_reflection_accept(app: CliAppContext, proposal_id: str) -> None:
    """Accept a proposal (marks it accepted; does not auto-apply)."""
    if app.proposal_store is None:
        click.echo("Proposal store not configured.", err=True)
        sys.exit(1)
    p = await app.proposal_store.get(proposal_id)
    if p is None:
        click.echo(f"Proposal not found: {proposal_id}", err=True)
        sys.exit(1)
    await app.proposal_store.update_status(
        proposal_id, "accepted", review_note="Accepted by operator"
    )
    click.echo(f"Accepted proposal {proposal_id}")


async def cmd_reflection_reject(app: CliAppContext, proposal_id: str, note: str | None) -> None:
    """Reject a proposal."""
    if app.proposal_store is None:
        click.echo("Proposal store not configured.", err=True)
        sys.exit(1)
    p = await app.proposal_store.get(proposal_id)
    if p is None:
        click.echo(f"Proposal not found: {proposal_id}", err=True)
        sys.exit(1)
    await app.proposal_store.update_status(
        proposal_id, "rejected", review_note=note or "Rejected by operator"
    )
    click.echo(f"Rejected proposal {proposal_id}")


async def cmd_reflection_defer(app: CliAppContext, proposal_id: str, until: str | None) -> None:
    """Defer a proposal."""
    if app.proposal_store is None:
        click.echo("Proposal store not configured.", err=True)
        sys.exit(1)
    p = await app.proposal_store.get(proposal_id)
    if p is None:
        click.echo(f"Proposal not found: {proposal_id}", err=True)
        sys.exit(1)
    note = "Deferred by operator"
    if until:
        note = f"Deferred by operator until {until}"
    await app.proposal_store.update_status(proposal_id, "deferred", review_note=note)
    click.echo(f"Deferred proposal {proposal_id}")


async def cmd_reflection_run(app: CliAppContext, now: bool) -> None:
    """Run reflection manually (requires --now)."""
    if not now:
        click.echo("Use --now to trigger reflection manually.", err=True)
        sys.exit(1)
    if app.proposal_store is None:
        click.echo("Proposal store not configured.", err=True)
        sys.exit(1)
    from hestia.config import ReflectionConfig
    from hestia.reflection.runner import ReflectionRunner

    cfg = app.config.reflection
    manual_cfg = ReflectionConfig(
        enabled=True,
        cron=cfg.cron,
        idle_minutes=cfg.idle_minutes,
        lookback_turns=cfg.lookback_turns,
        proposals_per_run=cfg.proposals_per_run,
        expire_days=cfg.expire_days,
        model_override=cfg.model_override,
    )
    runner = ReflectionRunner(
        config=manual_cfg,
        inference=app.inference,
        trace_store=app.trace_store,
        proposal_store=app.proposal_store,
    )
    proposals = await runner.run()
    if proposals:
        click.echo(f"Generated {len(proposals)} proposal(s):")
        for p in proposals:
            click.echo(f"  - {p.id}: {p.type} ({p.confidence:.2f}) {p.summary[:60]}")
    else:
        click.echo("No proposals generated.")


async def cmd_reflection_history(app: CliAppContext) -> None:
    """Show past proposals and their outcomes."""
    if app.proposal_store is None:
        click.echo("Proposal store not configured.", err=True)
        sys.exit(1)
    proposals = await app.proposal_store.list_by_status(limit=100)
    if not proposals:
        click.echo("No proposals found.")
        return
    click.echo(f"{'ID':<20} {'Type':<18} {'Status':<12} {'Confidence':<12} {'Summary'}")
    click.echo("-" * 90)
    for p in proposals:
        summary = p.summary[:35] + "..." if len(p.summary) > 35 else p.summary
        click.echo(f"{p.id:<20} {p.type:<18} {p.status:<12} {p.confidence:<12.2f} {summary}")
