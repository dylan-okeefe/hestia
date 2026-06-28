"""Lightweight, runtime-introspectable command registry for Hestia.

The registry maps slash-commands (``/quit``, ``/compact``, …) to async handlers
and exposes their metadata so help text and lint checks can be generated from
the source of truth: the handler docstrings.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from hestia.app import AppContext
    from hestia.core.types import Session
    from hestia.persistence.message_store import MessageStore
    from hestia.persistence.session_store import SessionStore


Handler = Callable[["CommandContext"], Awaitable[tuple[bool, "Session"]]]


class RegistryValidationError(Exception):
    """Raised when a registry fails the docstring-driven lint check."""


@dataclass(frozen=True)
class Command:
    """Metadata and handler for one slash-command.

    ``summary`` and ``long_help`` are derived from the handler's docstring so
    the registry stays introspectable without maintaining parallel help text.
    """

    name: str
    handler: Handler
    aliases: tuple[str, ...] = ()
    summary: str = ""
    long_help: str = ""
    category: str | None = None


@dataclass
class CommandContext:
    """Runtime context passed to every command handler."""

    session: Session
    session_store: SessionStore
    message_store: MessageStore | None = None
    app: AppContext | None = None
    instruction: str | None = None


class CommandRegistry:
    """Runtime-introspectable registry for slash-commands.

    Commands are registered by name and optional aliases. Lookup is
    case-insensitive so ``/QUIT`` resolves the same as ``/quit``.
    """

    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}
        self._aliases: dict[str, str] = {}

    def register(self, command: Command) -> None:
        """Register a command and its aliases.

        Raises:
            ValueError: If the command name or any alias is already registered.
        """
        name = command.name.lower()
        if name in self._commands:
            raise ValueError(f"Command {command.name!r} already registered")
        self._commands[name] = command
        for alias in command.aliases:
            alias_lower = alias.lower()
            if alias_lower in self._commands or alias_lower in self._aliases:
                raise ValueError(f"Alias {alias!r} conflicts with existing command")
            self._aliases[alias_lower] = name

    def get(self, name: str) -> Command | None:
        """Resolve a command by canonical name or alias."""
        name = name.lower()
        if name in self._commands:
            return self._commands[name]
        canonical = self._aliases.get(name)
        if canonical is not None:
            return self._commands[canonical]
        return None

    def commands(self) -> list[Command]:
        """Return all registered commands in insertion order."""
        return list(self._commands.values())

    async def handle(
        self,
        cmd: str,
        session: Session,
        session_store: SessionStore,
        message_store: MessageStore | None = None,
        app: AppContext | None = None,
    ) -> tuple[bool, Session]:
        """Parse ``cmd`` and dispatch to the matching handler.

        Unknown commands echo the legacy "Unknown command" message and return
        ``(False, session)`` unchanged.
        """
        base, instruction = _parse_meta_command(cmd)
        command = self.get(base)
        if command is None:
            click.echo(f"Unknown command: {base}. Type /help for a list.")
            return False, session

        ctx = CommandContext(
            session=session,
            session_store=session_store,
            message_store=message_store,
            app=app,
            instruction=instruction,
        )
        return await command.handler(ctx)


def _parse_meta_command(cmd: str) -> tuple[str, str | None]:
    """Split a /command from its optional trailing instruction.

    Examples:
      "/compact" -> ("/compact", None)
      "/compact keep the job criteria" -> ("/compact", "keep the job criteria")
    """
    stripped = cmd.strip()
    parts = stripped.split(None, 1)
    base = parts[0].lower() if parts else ""
    instruction = parts[1] if len(parts) > 1 else None
    return base, instruction


def _extract_summary(doc: str | None) -> str:
    """Return the first non-empty line of a docstring."""
    if not doc:
        return ""
    for line in doc.strip().splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def command_from_handler(
    *,
    name: str,
    handler: Handler,
    aliases: tuple[str, ...] = (),
    category: str | None = None,
) -> Command:
    """Build a :class:`Command` from a handler, using its docstring for help."""
    long_help = (handler.__doc__ or "").strip()
    summary = _extract_summary(handler.__doc__)
    return Command(
        name=name,
        handler=handler,
        aliases=aliases,
        summary=summary,
        long_help=long_help,
        category=category,
    )


def validate_registry(registry: CommandRegistry) -> None:
    """Validate that every registered command has a summary and long help.

    Raises:
        RegistryValidationError: If any command is missing docstring-derived
            metadata. This is the lint/drift gate for the command surface.
    """
    errors: list[str] = []
    for command in registry.commands():
        if not command.summary:
            errors.append(f"Command {command.name!r} is missing a summary (docstring)")
        if not command.long_help:
            errors.append(f"Command {command.name!r} is missing long_help (docstring)")
    if errors:
        raise RegistryValidationError("\n".join(errors))
