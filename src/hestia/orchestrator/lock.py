"""Per-session concurrency locks for the orchestrator."""

from __future__ import annotations

import asyncio
from typing import Any


class SessionLockManager:
    """Factory for per-session_id asyncio locks.

    Holds a non-reentrant lock per session for the lifetime of the
    process. Locks are created lazily and can be pruned for sessions
    that are archived or reset.
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def acquire(self, session_id: str) -> asyncio.Lock:
        """Return (and create if needed) the lock for *session_id*."""
        async with self._global_lock:
            lock = self._locks.get(session_id)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[session_id] = lock
        return lock

    def is_locked(self, session_id: str) -> bool:
        """Return True if a lock exists for *session_id* and is currently held.

        This is a non-blocking, synchronous probe intended for callers
        that must avoid awaiting a contended lock (e.g. the scheduler
        tick loop).
        """
        lock = self._locks.get(session_id)
        return lock.locked() if lock is not None else False

    def release_unused(self, session_id: str) -> None:
        """Prune the lock for *session_id* if it exists and is not held.

        This is best-effort: if a turn is still holding the lock, the
        entry is left in place so the lock object remains valid until it
        is naturally released.
        """
        lock = self._locks.get(session_id)
        if lock is None:
            return
        if not lock.locked():
            self._locks.pop(session_id, None)

    def __getstate__(self) -> dict[str, Any]:
        """Prevent accidental pickling of asyncio locks."""
        raise TypeError("SessionLockManager cannot be pickled")
