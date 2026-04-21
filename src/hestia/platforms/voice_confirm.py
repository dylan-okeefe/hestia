"""Verbal confirmation callback for voice conversations.

When a destructive tool (``terminal``, ``write_file``, ``email_send``) is
requested inside a voice session, Hestia speaks a confirmation prompt and
listens for a yes/no response in the next turn.

This is a simplified first-pass implementation.  It blocks the orchestrator
until the user responds (or a timeout expires).  A future refinement can
add concurrent text-channel fallback buttons and non-blocking deferred
confirmations.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING

from hestia.orchestrator.engine import ConfirmCallback

if TYPE_CHECKING:
    from hestia.platforms.discord_voice_runner import SpeakerSession

logger = logging.getLogger(__name__)

_YES_RE = re.compile(
    r"\b(yes|yeah|yep|sure|okay|ok|do it|go ahead|confirm|affirmative)\b",
    re.IGNORECASE,
)
_NO_RE = re.compile(
    r"\b(no|nope|nah|cancel|stop|abort|don'?t|negative|nevermind)\b",
    re.IGNORECASE,
)

_DEFAULT_TIMEOUT_SEC = 30.0
_MAX_PROMPT_RETRIES = 3


class VoiceConfirmCallback:
    """Confirmation callback that speaks prompts and parses voice responses."""

    def __init__(
        self,
        session: SpeakerSession,
        *,
        timeout_sec: float = _DEFAULT_TIMEOUT_SEC,
        max_retries: int = _MAX_PROMPT_RETRIES,
    ) -> None:
        self._session = session
        self._timeout_sec = timeout_sec
        self._max_retries = max_retries
        self._pending_future: asyncio.Future[str] | None = None

    async def request(
        self, tool_name: str, arguments: dict[str, object]
    ) -> bool:
        """Speak a confirmation prompt and wait for yes/no.

        Returns ``True`` if the user confirmed, ``False`` otherwise.
        """
        # Build a concise verbal prompt
        prompt = self._build_prompt(tool_name, arguments)

        for attempt in range(1, self._max_retries + 1):
            # Speak the prompt
            await self._session._speak(prompt)

            # Wait for the next transcript from the user
            try:
                response_text = await asyncio.wait_for(
                    self._wait_for_transcript(), timeout=self._timeout_sec
                )
            except TimeoutError:
                logger.warning(
                    "Voice confirmation timed out for tool '%s' (user=%s)",
                    tool_name,
                    self._session.user_id,
                )
                await self._session._speak("I didn't hear a response. Cancelling.")
                return False

            decision = self._parse_decision(response_text)
            if decision is True:
                return True
            if decision is False:
                await self._session._speak("Okay, cancelling.")
                return False

            # Unparsable — escalate prompt
            if attempt < self._max_retries:
                prompt = (
                    "I didn't catch that. Please say yes, no, or cancel."
                )
            else:
                await self._session._speak(
                    "I still didn't understand. Cancelling for safety."
                )
                return False

        return False

    def on_transcript(self, text: str) -> None:
        """Called by ``SpeakerSession`` when a new transcript arrives.

        If we are waiting for a confirmation response, fulfil the future.
        """
        if self._pending_future is not None and not self._pending_future.done():
            self._pending_future.set_result(text)

    def _build_prompt(self, tool_name: str, arguments: dict[str, object]) -> str:
        """Create a concise verbal prompt for the tool being requested."""
        # Summarise the action in plain language
        if tool_name == "email_send":
            to = arguments.get("to", "someone")
            subject = arguments.get("subject", "")
            return f"Should I send an email to {to} with subject: {subject}? Say yes or no."
        if tool_name == "terminal":
            cmd = arguments.get("command", "")
            return f"Should I run the command: {cmd}? Say yes or no."
        if tool_name == "write_file":
            path = arguments.get("path", "")
            return f"Should I write to file {path}? Say yes or no."
        return f"Should I run {tool_name}? Say yes or no."

    def _wait_for_transcript(self) -> asyncio.Future[str]:
        """Return a future that resolves with the next transcript."""
        self._pending_future = asyncio.get_running_loop().create_future()
        return self._pending_future

    @staticmethod
    def _parse_decision(text: str) -> bool | None:
        """Parse yes/no from transcript.  Returns ``None`` if unclear."""
        if _YES_RE.search(text):
            return True
        if _NO_RE.search(text):
            return False
        return None


def make_voice_confirm_callback(session: SpeakerSession) -> ConfirmCallback:
    """Factory returning a ``ConfirmCallback`` wired to *session*.

    The returned callable matches the standard ``ConfirmCallback`` signature
    ``(tool_name: str, arguments: dict[str, object]) -> Awaitable[bool]``.
    """
    vcc = VoiceConfirmCallback(session)

    async def callback(tool_name: str, arguments: dict[str, object]) -> bool:
        return await vcc.request(tool_name, arguments)

    return callback
