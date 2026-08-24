"""Scope helpers for memory maintenance.

Two-tier memory scopes: a global pool (``is_global=True``) and a topic-scoped
pool (``is_global=False`` with topic associations). Maintenance passes must not
cross these scopes when deduplicating, superseding, or applying the protected
set.
"""

from __future__ import annotations

from hestia.memory.store import Memory

GLOBAL_SCOPE_KEY = ("__global__",)


def memory_scope_key(memory: Memory, topic_ids: list[str]) -> tuple[str, ...]:
    """Return a hashable scope key for a memory.

    Global memories share one scope regardless of topic associations.
    Topic-scoped memories are keyed by their sorted topic IDs so maintenance
    operates within each topic set independently.
    """
    if memory.is_global:
        return GLOBAL_SCOPE_KEY
    return tuple(sorted(topic_ids))


def format_scope_key(key: tuple[str, ...]) -> str:
    """Return a human-readable scope string for trace details."""
    if key == GLOBAL_SCOPE_KEY:
        return "global"
    return ",".join(key)
