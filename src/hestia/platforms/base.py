"""Abstract base class for platform adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable
from typing import Any, Protocol


class IncomingMessageCallback(Protocol):
    """Callback invoked by a platform when a message arrives.

    Signature::

        (platform_name, platform_user, message_text,
         sender_platform_user=None, session_title=None, images=None) -> None

    - ``sender_platform_user`` is the individual sender's platform ID in group
      chats; None in private chats.
    - ``session_title`` is an optional display name for the conversation
      (e.g., Telegram group title).
    - ``images`` is an optional list of ``data:image/jpeg;base64,...`` URLs
      (L234 vision). Callers that predate vision pass ``None`` (or omit the
      argument at runtime against older 5-parameter callbacks); the defaults
      on concrete implementations keep them source-compatible.

    NOTE: the parameters are declared without defaults here because mypy
    rejects function-to-callback-protocol assignability when the protocol's
    ``__call__`` carries default arguments. Concrete implementations (e.g.
    ``PlatformRunner.on_message``) provide the defaults. Parameter names
    intentionally mirror ``PlatformRunner.on_message`` — mypy requires
    positional names to match for callback-protocol assignability.
    """

    def __call__(
        self,
        platform_name_arg: str,
        platform_user: str,
        text: str,
        sender_platform_user: str | None,
        session_title: str | None,
        images: list[str] | None,
    ) -> Awaitable[None]: ...


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
                        The platform passes (platform_name, platform_user, text,
                        sender_platform_user, session_title, images) — the last
                        three are optional; images carries JPEG data URLs when
                        the message had photo attachments (L234 vision).
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
    async def edit_message(
        self, user: str, msg_id: str, text: str, **kwargs: Any
    ) -> None:
        """Edit a previously sent message in-place.

        For platforms that don't support editing (CLI), this is a no-op
        or prints a new line.
        """
        ...

    @abstractmethod
    async def send_error(self, user: str, text: str) -> None:
        """Send an error message to a user."""
        ...

    async def send_system_warning(self, user: str, text: str) -> None:
        """Send an out-of-band system warning to a user.

        Default implementation prepends ⚠️ and routes through send_message.
        Platforms may override for distinct formatting (e.g., red text,
        separate notification channel).
        """
        await self.send_message(user, f"⚠️ {text}")

    async def set_typing(self, user: str, typing: bool = True) -> None:
        """Set typing indicator for a user/room. No-op by default."""
        return None

    async def delete_message(self, user: str, msg_id: str) -> None:
        """Delete a previously sent message. No-op by default."""
        return None
