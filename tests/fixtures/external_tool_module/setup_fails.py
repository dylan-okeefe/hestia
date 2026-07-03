"""External tool module whose setup hook fails."""

from __future__ import annotations

from hestia.tools.registry import ToolRegistry


def setup(context: object) -> None:
    """Deliberately fail so registration is skipped."""
    raise RuntimeError("setup failed on purpose")


def register(registry: ToolRegistry) -> None:
    """Should never be called because setup fails."""
    raise AssertionError("register should not be called after setup failure")
