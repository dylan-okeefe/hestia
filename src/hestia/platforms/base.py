"""Abstract base class for platform adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable


# Callback type for incoming messages from the platform
IncomingMessageCallback = Callable[[str, str, str], Awaitable[None]]
# (platform_name, platform_user, message_text) -> None


class Platform(ABC):
    """Base class for platform adapters (CLI, Telegram, Matrix, etc.).

    A platform is responsible for:
      - Receiving messages from users and forwarding them to the orchestrator
      - Delivering responses back to users
      - Optionally: editing status messages in-place, sending errors
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Platform identifier (e.g., 'cli', 'telegram', 'matrix')."""
        ...

    @abstractmethod
    async def start(self, on_message: IncomingMessageCallback) -> None:
        """Start listening for messages.

        Args:
            on_message: Callback to invoke when a message arrives.
                        The platform passes (platform_name, platform_user, text).
        """
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the adapter and clean up resources."""
        ...

    @abstractmethod
    async def send_message(self, user: str, text: str) -> str:
        """Send a message to a user. Returns a message ID for editing."""
        ...

    @abstractmethod
    async def edit_message(self, user: str, msg_id: str, text: str) -> None:
        """Edit a previously sent message in-place.

        For platforms that don't support editing (CLI), this is a no-op
        or prints a new line.
        """
        ...

    @abstractmethod
    async def send_error(self, user: str, text: str) -> None:
        """Send an error message to a user."""
        ...
