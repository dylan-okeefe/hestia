"""Path validation utilities for file tools."""

from pathlib import Path


def check_path_allowed(path: str, allowed_roots: list[str]) -> str | None:
    """Check if a path is within allowed roots.

    Args:
        path: The path to check
        allowed_roots: List of allowed root directories

    Returns:
        Error message if path is outside allowed roots, None if allowed
    """
    resolved = Path(path).resolve()
    for root in allowed_roots:
        root_resolved = Path(root).resolve()
        try:
            resolved.relative_to(root_resolved)
            return None  # Path is allowed
        except ValueError:
            continue  # Try next root

    roots_str = ", ".join(allowed_roots)
    return f"Access denied: {path} is outside allowed roots ({roots_str})"
