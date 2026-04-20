"""Allow-list matching and validation for platform adapters.

Supports Unix shell-style wildcards (*, ?, [seq]) and platform-specific
validation rules.
"""

from __future__ import annotations

import fnmatch
import re


def match_allowlist(
    patterns: list[str],
    value: str,
    case_sensitive: bool = True,
) -> bool:
    """Check if ``value`` matches any pattern in ``patterns``.

    Patterns use Unix shell-style wildcards:
    - ``*`` matches everything
    - ``?`` matches any single character
    - ``[seq]`` matches any character in seq

    An empty pattern list denies all (secure default).

    Args:
        patterns: List of allow-list patterns
        value: The value to match (e.g. user ID, room ID)
        case_sensitive: Whether matching is case-sensitive

    Returns:
        True if the value matches at least one pattern
    """
    if not patterns:
        return False

    for pattern in patterns:
        if case_sensitive:
            if fnmatch.fnmatchcase(value, pattern):
                return True
        else:
            if fnmatch.fnmatch(value.lower(), pattern.lower()):
                return True

    return False


# --- Platform-specific validators ---


def validate_telegram_user_id(user_id: str) -> bool:
    """Validate a Telegram numeric user ID.

    Telegram user IDs are positive integers.
    """
    return user_id.isdigit()


def validate_telegram_username(username: str) -> bool:
    """Validate a Telegram username.

    Usernames are 5-32 characters, alphanumeric + underscore.
    The ``@`` prefix is optional here (stripped before check).
    """
    clean = username.lstrip("@")
    if not clean:
        return False
    return bool(re.fullmatch(r"[a-zA-Z0-9_]{5,32}", clean))


def validate_matrix_room_id(room_id: str) -> bool:
    """Validate a Matrix room ID or alias.

    Room IDs start with ``!`` and contain a server part after ``:``.
    Room aliases start with ``#`` and contain a server part after ``:``.
    """
    if not room_id:
        return False
    # Must contain a colon for the server part
    if ":" not in room_id:
        return False
    # Must start with ! or #
    return room_id.startswith(("!", "#"))


def validate_matrix_room_alias(alias: str) -> bool:
    """Validate a Matrix room alias.

    Aliases start with ``#`` and contain a server part after ``:``.
    """
    if not alias:
        return False
    if ":" not in alias:
        return False
    return alias.startswith("#")
