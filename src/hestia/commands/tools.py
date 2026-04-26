"""Tool (skill) related command implementations."""

from __future__ import annotations

import sys

import click

from hestia.app import CliAppContext
from hestia.commands._shared import _format_utc
from hestia.skills.state import SkillState


async def cmd_skill_list(app: CliAppContext, state_filter: str | None, show_all: bool) -> None:
    """List skills with their states."""
    if app.skill_store is None:
        click.echo("Skill store not available", err=True)
        sys.exit(1)
    skill_state = None
    if state_filter:
        try:
            skill_state = SkillState(state_filter.lower())
        except ValueError:
            click.echo(f"Invalid state: {state_filter}", err=True)
            sys.exit(1)
    records = await app.skill_store.list_all(
        state=skill_state,
        exclude_disabled=not show_all,
    )
    if not records:
        click.echo("No skills found.")
        return
    click.echo(
        f"{'Name':<20} {'State':<12} {'Runs':<6} {'Fails':<6} {'Description'}"
    )
    click.echo("-" * 80)
    for record in records:
        desc = record.description
        if len(desc) > 35:
            desc = desc[:35] + "..."
        click.echo(
            f"{record.name:<20} {record.state.value:<12} "
            f"{record.run_count:<6} {record.failure_count:<6} {desc}"
        )


async def cmd_skill_show(app: CliAppContext, name: str) -> None:
    """Show skill details."""
    if app.skill_store is None:
        click.echo("Skill store not available", err=True)
        sys.exit(1)
    record = await app.skill_store.get_by_name(name)
    if record is None:
        click.echo(f"Skill not found: {name}", err=True)
        sys.exit(1)
    click.echo(f"Name:        {record.name}")
    click.echo(f"Description: {record.description}")
    click.echo(f"State:       {record.state.value}")
    click.echo(f"File path:   {record.file_path}")
    click.echo(f"Created:     {_format_utc(record.created_at)}")
    click.echo(f"Last run:    {_format_utc(record.last_run_at)}")
    click.echo(f"Run count:   {record.run_count}")
    click.echo(f"Failures:    {record.failure_count}")
    click.echo(f"Tools:       {', '.join(record.required_tools) or 'none'}")
    click.echo(f"Caps:        {', '.join(record.capabilities) or 'none'}")


async def cmd_skill_promote(app: CliAppContext, name: str) -> None:
    """Advance skill state (draft -> tested -> trusted)."""
    if app.skill_store is None:
        click.echo("Skill store not available", err=True)
        sys.exit(1)
    record = await app.skill_store.get_by_name(name)
    if record is None:
        click.echo(f"Skill not found: {name}", err=True)
        sys.exit(1)
    transitions = {
        SkillState.DRAFT: SkillState.TESTED,
        SkillState.TESTED: SkillState.TRUSTED,
        SkillState.TRUSTED: SkillState.TRUSTED,
        SkillState.DEPRECATED: SkillState.TESTED,
        SkillState.DISABLED: SkillState.DRAFT,
    }
    new_state = transitions.get(record.state)
    if new_state is None:
        click.echo(
            f"Skill '{name}' has no valid promotion path from "
            f"'{record.state.value}'",
            err=True,
        )
        sys.exit(1)
    if new_state == record.state:
        click.echo(f"Skill '{name}' is already at state '{record.state.value}'")
        return
    await app.skill_store.update_state(name, new_state)
    click.echo(f"Promoted '{name}': {record.state.value} -> {new_state.value}")


async def cmd_skill_demote(app: CliAppContext, name: str) -> None:
    """Move skill back one state."""
    if app.skill_store is None:
        click.echo("Skill store not available", err=True)
        sys.exit(1)
    record = await app.skill_store.get_by_name(name)
    if record is None:
        click.echo(f"Skill not found: {name}", err=True)
        sys.exit(1)
    transitions = {
        SkillState.DRAFT: SkillState.DISABLED,
        SkillState.TESTED: SkillState.DRAFT,
        SkillState.TRUSTED: SkillState.TESTED,
        SkillState.DEPRECATED: SkillState.DEPRECATED,
        SkillState.DISABLED: SkillState.DISABLED,
    }
    new_state = transitions.get(record.state)
    if new_state is None:
        click.echo(
            f"Skill '{name}' has no valid demotion path from "
            f"'{record.state.value}'",
            err=True,
        )
        sys.exit(1)
    if new_state == record.state:
        click.echo(f"Skill '{name}' is already at state '{record.state.value}'")
        return
    await app.skill_store.update_state(name, new_state)
    click.echo(f"Demoted '{name}': {record.state.value} -> {new_state.value}")


async def cmd_skill_disable(app: CliAppContext, name: str) -> None:
    """Disable a skill without removing it."""
    if app.skill_store is None:
        click.echo("Skill store not available", err=True)
        sys.exit(1)
    record = await app.skill_store.get_by_name(name)
    if record is None:
        click.echo(f"Skill not found: {name}", err=True)
        sys.exit(1)
    if record.state == SkillState.DISABLED:
        click.echo(f"Skill '{name}' is already disabled")
        return
    await app.skill_store.update_state(name, SkillState.DISABLED)
    click.echo(f"Disabled skill: {name}")
