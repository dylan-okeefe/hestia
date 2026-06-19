"""Write-time sanitizer for memory store entries."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SanitizerResult:
    """Outcome of sanitizing a candidate memory entry.

    Attributes:
        accepted: True when the content is acceptable to store.
        rejected: True when the content was rejected (mutually exclusive with accepted).
        content: The cleaned content when accepted; None when rejected.
        reason: Human-readable rejection reason when rejected; None when accepted.
    """

    accepted: bool
    rejected: bool
    content: str | None
    reason: str | None

    @classmethod
    def accept(cls, content: str) -> SanitizerResult:
        """Return an accepted result with cleaned content."""
        return cls(accepted=True, rejected=False, content=content, reason=None)

    @classmethod
    def reject(cls, reason: str) -> SanitizerResult:
        """Return a rejected result with a reason."""
        return cls(accepted=False, rejected=True, content=None, reason=reason)


class MemorySanitizer:
    """Sanitize candidate memory content before it reaches the store.

    The sanitizer rejects tool-call XML, raw conversation dumps, and trivially
    low-value strings. Clean prose facts and structured key-value summaries are
    preserved. All decisions are returned as a ``SanitizerResult`` so callers
    can log or surface them without raising exceptions.
    """

    DEFAULT_MIN_LENGTH = 8

    # Filler words that, when repeated, indicate low-value content.
    _FILLER_WORDS = frozenset(
        {
            "um",
            "uh",
            "ah",
            "er",
            "like",
            "so",
            "yeah",
            "yep",
            "nope",
            "ok",
            "okay",
        }
    )

    def __init__(self, min_length: int = DEFAULT_MIN_LENGTH) -> None:
        self.min_length = min_length

    def sanitize(self, content: str) -> SanitizerResult:
        """Sanitize candidate memory content.

        Args:
            content: The raw memory content to evaluate.

        Returns:
            A ``SanitizerResult`` describing whether and how the content may be stored.
        """
        if not isinstance(content, str):
            return SanitizerResult.reject("content must be a string")

        text = content.strip()

        # Trivial content checks ------------------------------------------------
        if not text:
            return SanitizerResult.reject("empty or whitespace-only content")

        if len(text) < self.min_length:
            return SanitizerResult.reject(
                f"content shorter than {self.min_length} characters"
            )

        if self._is_pure_punctuation(text):
            return SanitizerResult.reject("content is pure punctuation")

        if self._is_repeated_filler(text):
            return SanitizerResult.reject("content is repeated filler words")

        # XML / tool-call checks ------------------------------------------------
        if self._has_tool_call_xml(text):
            return SanitizerResult.reject("content contains tool-call XML")

        if self._has_xml_declaration(text):
            return SanitizerResult.reject("content contains XML declaration")

        if self._has_unclosed_tags(text):
            return SanitizerResult.reject("content contains unclosed HTML/XML tags")

        # Raw turn-dump checks --------------------------------------------------
        if self._is_raw_turn_dump(text):
            return SanitizerResult.reject("content looks like a raw turn dump")

        return SanitizerResult.accept(text)

    def _is_pure_punctuation(self, text: str) -> bool:
        """Return True when the text contains no letters or digits."""
        return not any(char.isalnum() for char in text)

    def _is_repeated_filler(self, text: str) -> bool:
        """Return True for content that is mostly repeated filler words."""
        words = re.findall(r"[a-zA-Z']+", text.lower())
        if not words:
            return False

        unique_words = set(words)

        # Very low vocabulary with several words is likely filler.
        if len(words) >= 3 and len(unique_words) <= 2:
            return True

        # A short filler word repeated three or more times.
        for word in unique_words:
            if word in self._FILLER_WORDS and words.count(word) >= 3:
                return True

        # A single non-filler word repeated many times (e.g. "hello hello hello").
        return bool(len(unique_words) == 1 and len(words) >= 3)

    def _has_tool_call_xml(self, text: str) -> bool:
        """Return True when the text contains tool-call XML tags or fragments."""
        # Function-style tags seen in some model outputs.
        return bool(
            re.search(r"</?tool_call[\s>]", text, re.IGNORECASE)
            or re.search(r"</?function[\s>]", text, re.IGNORECASE)
            or re.search(r"</?[a-z_]+_tool[\s>]", text, re.IGNORECASE)
        )

    def _has_xml_declaration(self, text: str) -> bool:
        """Return True when the text contains an XML/DOCTYPE declaration."""
        return bool(re.search(r"<\?xml|<!DOCTYPE", text, re.IGNORECASE))

    def _has_unclosed_tags(self, text: str) -> bool:
        """Return True when the text contains HTML/XML tags or unclosed brackets."""
        # Any tag-like sequence is suspicious in prose memory content.
        if re.search(r"</?[a-zA-Z][^>]*>", text):
            return True

        # An opening bracket that looks like a tag but is never closed.
        return bool(self._has_unclosed_open_bracket(text))

    def _has_unclosed_open_bracket(self, text: str) -> bool:
        """Return True when a tag-like '<' has no matching '>'."""
        depth = 0
        i = 0
        length = len(text)
        while i < length:
            if text[i] == "<":
                if i + 1 < length and (
                    text[i + 1].isalpha() or text[i + 1] in "!/?"
                ):
                    depth += 1
                i += 1
            elif text[i] == ">":
                if depth > 0:
                    depth -= 1
                i += 1
            else:
                i += 1
        return depth != 0

    def _is_raw_turn_dump(self, text: str) -> bool:
        """Return True when the text looks like a raw assistant/tool transcript."""
        lower = text.lower()

        # JSON/XML role fields are a strong signal of a conversation dump.
        if re.search(r"\brole\b\s*['\"]?\s*[:=]\s*['\"]", lower):
            return True

        # Multiple role markers or repeated markers from the same role.
        role_markers = ("user:", "assistant:", "system:")
        marker_hits = sum(1 for marker in role_markers if marker in lower)
        if marker_hits >= 2:
            return True

        for marker in role_markers:
            if lower.count(marker) >= 2:
                return True

        # Alternating "User" / "Assistant" labels (case-insensitive, as labels).
        user_labels = len(re.findall(r"\buser\b", lower))
        assistant_labels = len(re.findall(r"\bassistant\b", lower))
        return bool(user_labels >= 1 and assistant_labels >= 1)
