"""Text-scrubbing utilities for regression fixtures and diagnostics."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable


# ---------------------------------------------------------------------------
# Scrubbing rules
# ---------------------------------------------------------------------------


def _replace_home_paths(text: str) -> str:
    """Replace /home/<username>/... with /home/<user>/..."""
    return re.sub(r"/home/[^/\s]+/", "/home/<user>/", text)


def _replace_windows_home_paths(text: str) -> str:
    """Replace C:\\Users\\<username>\\... with C:\\Users\\<user>\\..."""
    return re.sub(r"[A-Za-z]:\\Users\\[^\\\s]+\\", r"C:\\Users\\<user>\\", text)


def _replace_emails(text: str) -> str:
    return re.sub(
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "<email>",
        text,
    )


def _replace_ips(text: str) -> str:
    return re.sub(
        r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        "<ip>",
        text,
    )


def _replace_telegram_tokens(text: str) -> str:
    """Replace Telegram bot tokens like 123456789:ABCDef..."""
    return re.sub(
        r"\b\d{9,}:[A-Za-z0-9_-]{30,}\b",
        "<telegram-token>",
        text,
    )


def _replace_api_keys(text: str) -> str:
    """Redact common API key shapes (hex or base64-ish, 32+ chars)."""
    return re.sub(
        r"\b(?:api[_-]?key|token|secret|password)\s*[=:]\s*['\"]?([A-Za-z0-9_/+.-]{32,})['\"]?",
        lambda m: f"{m.group(0).split(m.group(1))[0]}<redacted>",
        text,
        flags=re.IGNORECASE,
    )


_SCRUBBERS: list[Callable[[str], str]] = [
    _replace_home_paths,
    _replace_windows_home_paths,
    _replace_emails,
    _replace_ips,
    _replace_telegram_tokens,
    _replace_api_keys,
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scrub_text(text: str) -> str:
    """Apply all scrubbing rules to ``text``."""
    for scrubber in _SCRUBBERS:
        text = scrubber(text)
    return text


def scrub_fixture_file(path: Path, *, dry_run: bool = False) -> bool:
    """Scrub a single fixture file. Returns True if changes were made."""
    original = path.read_text(encoding="utf-8")
    cleaned = scrub_text(original)
    changed = original != cleaned
    if changed and not dry_run:
        path.write_text(cleaned, encoding="utf-8")
    return changed
