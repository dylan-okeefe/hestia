"""Narrated tour command handlers and ephemeral cursor storage for Hestia.

The tour is a pure-narration walkthrough: it only shows curated prose and
never gates progression on user action. State is kept in an in-memory store
keyed by ``(platform, platform_user)`` so the tour works without adding a new
persistence table.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

import click

from hestia.commands.registry import CommandContext

if TYPE_CHECKING:
    from hestia.core.types import Session


TourStep = Callable[[], str]


class TourStore:
    """Ephemeral cursor store for narrated tours.

    Cursors are keyed by ``(platform, platform_user)`` so DMs and group rooms
    are independent, and a process restart naturally clears all tours. The
    cursor value is the *next* step index to show; ``/tour`` resets it to 1
    and immediately displays step 1 (index 0).
    """

    def __init__(self) -> None:
        self._cursors: dict[tuple[str, str], int] = {}

    def _key(self, platform: str, platform_user: str) -> tuple[str, str]:
        return (platform.lower(), platform_user)

    def get(self, platform: str, platform_user: str) -> int | None:
        """Return the next step index for a conversation, or ``None``."""
        return self._cursors.get(self._key(platform, platform_user))

    def set(self, platform: str, platform_user: str, cursor: int) -> None:
        """Set the next step index for a conversation."""
        self._cursors[self._key(platform, platform_user)] = cursor

    def clear(self, platform: str, platform_user: str) -> None:
        """Clear the cursor for a conversation."""
        self._cursors.pop(self._key(platform, platform_user), None)


# Module-level singleton shared by command handlers and platform adapters.
DEFAULT_TOUR_STORE = TourStore()


def get_tour_store() -> TourStore:
    """Return the default tour store."""
    return DEFAULT_TOUR_STORE


def _step_welcome() -> str:
    return (
        "Welcome to the Hestia tour. Over the next few messages I'll walk you "
        "through the main things you can do here. Type /continue to move to the "
        "next stop, or /endtour at any time to stop."
    )


def _step_commands_reference() -> str:
    return (
        "Hestia understands slash commands. Type /commands (or /help) any time "
        "to see the full list with short descriptions. It's the fastest way to "
        "remember what's available without guessing."
    )


def _step_chat_and_session() -> str:
    return (
        "Every conversation lives in a session. You can chat naturally, and "
        "Hestia keeps context across turns. Use /session to see the current "
        "session details, /history to review the message history, and /reset "
        "to archive the current session and start fresh."
    )


def _step_memory() -> str:
    return (
        "Hestia can remember facts across sessions. When a session ends, key "
        "details are summarized into long-term memory. Use /refresh to rebuild "
        "the memory epoch for the current session from those stored memories."
    )


def _step_context_management() -> str:
    return (
        "Long conversations can outgrow the model's context window. Use "
        "/compact to summarize and archive older messages in place, and /tokens "
        "to check token usage for the most recent turn."
    )


def _step_tools() -> str:
    return (
        "Beyond chatting, Hestia can use tools: search the web, read and write "
        "files, run code, send messages, and more. Ask for something directly "
        "and Hestia will pick the right capability."
    )


def _step_workflows_and_scheduling() -> str:
    return (
        "For repeating work, Hestia supports scheduled tasks and workflows. "
        "You can set up cron-style prompts, build multi-step workflows, and "
        "have Hestia run them autonomously in the background."
    )


def _step_platforms_and_voice() -> str:
    return (
        "You can reach Hestia from the CLI REPL, Telegram, or Matrix. On "
        "Telegram you can also send voice messages for speech-to-text input "
        "and receive voice replies."
    )


def _step_wrap_up() -> str:
    return (
        "That's the tour. You can restart it any time with /tour, list "
        "commands with /commands, reset the conversation with /reset, or end "
        "the session with /quit (or /exit)."
    )


# Static list of tour steps. The order here is the order users see.
TOUR_STEPS: list[TourStep] = [
    _step_welcome,
    _step_commands_reference,
    _step_chat_and_session,
    _step_memory,
    _step_context_management,
    _step_tools,
    _step_workflows_and_scheduling,
    _step_platforms_and_voice,
    _step_wrap_up,
]


_COMMAND_PATTERN = re.compile(r"/[a-z][a-z0-9_]*")


def tour_command_coverage() -> set[str]:
    """Return the slash-command names mentioned across all tour steps.

    This is a drift guard helper: tests can compare it against the registry to
    make sure new commands are surfaced in the tour.
    """
    text = " ".join(step() for step in TOUR_STEPS)
    return set(_COMMAND_PATTERN.findall(text))


# Major capabilities that should be surfaced by the tour prose, independent of
# the slash-command registry. The drift guard checks that each one appears.
TOUR_CAPABILITY_KEYWORDS: tuple[str, ...] = (
    "commands",
    "session",
    "history",
    "reset",
    "memory",
    "compact",
    "tokens",
    "tools",
    "workflows",
    "scheduled",
    "voice",
    "telegram",
    "matrix",
    "cli",
)


def tour_capability_coverage() -> set[str]:
    """Return the major capability keywords mentioned across all tour steps."""
    text = " ".join(step() for step in TOUR_STEPS).lower()
    return {keyword for keyword in TOUR_CAPABILITY_KEYWORDS if keyword in text}


def _render_step(step_index: int) -> str:
    """Render a single tour step by index."""
    if not 0 <= step_index < len(TOUR_STEPS):
        raise ValueError(f"Invalid tour step index: {step_index}")
    return TOUR_STEPS[step_index]()


def _header(step_index: int) -> str:
    """Return the 'Step N of M' header."""
    return f"Step {step_index + 1} of {len(TOUR_STEPS)}"


def render_tour_start(
    store: TourStore,
    platform: str,
    platform_user: str,
    group_room: bool = False,
) -> str:
    """Start the tour and return the message to send.

    If ``group_room`` is ``True``, the tour refuses to start and tells the
    user to use a direct message.
    """
    if group_room:
        return "This tour is available in direct messages only."

    store.set(platform, platform_user, 1)
    return f"{_header(0)}\n\n{_render_step(0)}"


def render_tour_continue(
    store: TourStore,
    platform: str,
    platform_user: str,
    group_room: bool = False,
) -> str:
    """Advance the tour by one step and return the message to send.

    Returns a completion message and clears the cursor when the tour is
    finished. Returns a "no tour running" message when there is no cursor or
    when invoked from a group room.
    """
    if group_room:
        return "No tour running."

    cursor = store.get(platform, platform_user)
    if cursor is None:
        return "No tour running."

    if cursor >= len(TOUR_STEPS):
        store.clear(platform, platform_user)
        return "Tour complete."

    text = f"{_header(cursor)}\n\n{_render_step(cursor)}"
    store.set(platform, platform_user, cursor + 1)
    return text


def render_tour_end(
    store: TourStore,
    platform: str,
    platform_user: str,
    group_room: bool = False,
) -> str:
    """End the tour and return the message to send.

    Returns a "no tour running" message when there is no cursor or when
    invoked from a group room.
    """
    if group_room:
        return "No tour running."

    if store.get(platform, platform_user) is None:
        return "No tour running."

    store.clear(platform, platform_user)
    return "Tour ended."


async def _cmd_tour(ctx: CommandContext) -> tuple[bool, Session]:
    """Start the narrated Hestia tour from step 1."""
    text = render_tour_start(
        get_tour_store(),
        ctx.session.platform,
        ctx.session.platform_user,
        group_room=ctx.group_room,
    )
    click.echo(text)
    return False, ctx.session


async def _cmd_continue(ctx: CommandContext) -> tuple[bool, Session]:
    """Continue the narrated Hestia tour by one step."""
    text = render_tour_continue(
        get_tour_store(),
        ctx.session.platform,
        ctx.session.platform_user,
        group_room=ctx.group_room,
    )
    click.echo(text)
    return False, ctx.session


async def _cmd_endtour(ctx: CommandContext) -> tuple[bool, Session]:
    """End the narrated Hestia tour and clear the cursor."""
    text = render_tour_end(
        get_tour_store(),
        ctx.session.platform,
        ctx.session.platform_user,
        group_room=ctx.group_room,
    )
    click.echo(text)
    return False, ctx.session


def validate_tour_coverage(
    command_names: Iterable[str],
    required_capabilities: Iterable[str] | None = None,
) -> None:
    """Validate that the tour covers the expected commands and capabilities.

    Args:
        command_names: Canonical command names that should appear in tour text.
        required_capabilities: Major capability keywords that should appear.

    Raises:
        AssertionError: If any command or capability is missing from the tour.
    """
    commands_found = tour_command_coverage()
    missing_commands = sorted(name for name in command_names if name.lower() not in {c.lower() for c in commands_found})
    if missing_commands:
        raise AssertionError(f"Tour is missing coverage for commands: {', '.join(missing_commands)}")

    if required_capabilities is not None:
        capabilities_found = tour_capability_coverage()
        missing_capabilities = sorted(cap for cap in required_capabilities if cap.lower() not in capabilities_found)
        if missing_capabilities:
            raise AssertionError(f"Tour is missing coverage for capabilities: {', '.join(missing_capabilities)}")
