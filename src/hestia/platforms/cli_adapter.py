"""CLI platform adapter."""

from __future__ import annotations

import click

from hestia.platforms.base import IncomingMessageCallback, Platform


class CliPlatform(Platform):
    """CLI platform adapter. Blocking REPL for local testing."""

    @property
    def name(self) -> str:
        return "cli"

    async def start(self, on_message: IncomingMessageCallback) -> None:
        """Not used directly — CLI drives via the REPL loop in cli.py."""
        pass  # CLI is pull-based (prompt), not push-based (listener)

    async def stop(self) -> None:
        pass

    async def send_message(self, user: str, text: str) -> str:
        """Print response to stdout. Returns a placeholder msg_id."""
        click.echo(f"\nAssistant: {text}\n")
        return "cli-msg"  # CLI doesn't support editing

    async def edit_message(self, user: str, msg_id: str, text: str) -> None:
        """CLI doesn't support in-place editing. Print new line instead."""
        click.echo(f"\nAssistant: {text}\n")

    async def send_error(self, user: str, text: str) -> None:
        click.echo(f"\nError: {text}\n", err=True)
