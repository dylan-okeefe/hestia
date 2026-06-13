"""Tests that UPGRADE.md matches the current package state."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hestia.cli import cli

UPGRADE_PATH = Path("UPGRADE.md")
PYPROJECT_PATH = Path("pyproject.toml")
VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)
HEADING_RE = re.compile(r"^##\s+(v.+)$", re.MULTILINE)
HESTIA_COMMAND_RE = re.compile(r"`hestia\s+([a-z][a-z0-9_-]*)(?:\s+([a-z][a-z0-9_-]*))?")


def _current_package_version() -> str:
    """Read version from pyproject.toml."""
    text = PYPROJECT_PATH.read_text()
    match = VERSION_RE.search(text)
    if not match:
        pytest.fail("Could not find version in pyproject.toml")
    return match.group(1)


def _known_cli_commands() -> set[str]:
    """Flatten click commands/groups into dotted command strings."""
    commands: set[str] = set()

    def collect(group: click.Group, prefix: str = "") -> None:
        for name, cmd in group.commands.items():
            full = f"{prefix}{name}" if not prefix else f"{prefix} {name}"
            commands.add(full)
            if isinstance(cmd, click.Group):
                collect(cmd, full)

    import click

    collect(cli)
    return commands


def test_upgrade_top_heading_matches_package_version() -> None:
    """The first version heading in UPGRADE.md must reference the current version."""
    version = _current_package_version()
    text = UPGRADE_PATH.read_text()
    headings = HEADING_RE.findall(text)
    if not headings:
        pytest.fail("No version headings found in UPGRADE.md")

    top = headings[0]
    assert version in top, (
        f"Top UPGRADE.md version heading {top!r} does not mention "
        f"current package version {version}"
    )


def test_upgrade_mentions_only_known_cli_commands() -> None:
    """Every `hestia ...` command referenced in UPGRADE.md must exist in hestia.cli."""
    known = _known_cli_commands()
    text = UPGRADE_PATH.read_text()
    unknown: set[str] = set()

    for match in HESTIA_COMMAND_RE.finditer(text):
        first = match.group(1)
        second = match.group(2)
        if second:
            command = f"{first} {second}"
        else:
            command = first
        if command not in known:
            unknown.add(command)

    if unknown:
        pytest.fail(
            f"UPGRADE.md references unknown CLI commands: {sorted(unknown)}"
        )
