"""Per-session concurrency locks for the orchestrator."""

from __future__ import annotations

import asyncio
from typing import Any


class SessionLockManager:
    """Factory for per-session_id asyncio locks.

    Holds a non-reentrant lock per session for the lifetime of the process.
    Locks are created lazily. Callers that obtain a lock via :meth:`acquire`
    hold an *interest reference* until they call :meth:`unref`; pruning via
    :meth:`release_unused` is suppressed while any reference or waiter exists,
    so a pending contender can never be stranded on an orphaned lock object.
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._refs: dict[str, int] = {}
        self._global_lock = asyncio.Lock()

    async def acquire(self, session_id: str) -> asyncio.Lock:
        """Return (and create if needed) the lock for *session_id*.

        Registers one interest reference; pair with :meth:`unref` when the
        critical section ends.
        """
        async with self._global_lock:
            lock = self._locks.get(session_id)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[session_id] = lock
            self._refs[session_id] = self._refs.get(session_id, 0) + 1
        return lock

    def unref(self, session_id: str) -> None:
        """Drop one interest reference previously registered by acquire()."""
        count = self._refs.get(session_id, 0)
        if count <= 1:
            self._refs.pop(session_id, None)
        else:
            self._refs[session_id] = count - 1

    def is_locked(self, session_id: str) -> bool:
        """Return True if a lock exists for *session_id* and is currently held.

        This is a non-blocking, synchronous probe intended for callers
        that must avoid awaiting a contended lock (e.g. the scheduler
        tick loop).
        """
        lock = self._locks.get(session_id)
        return lock.locked() if lock is not None else False

    def release_unused(self, session_id: str) -> None:
        """Prune the lock for *session_id* when it is truly idle.

        Best-effort on three conditions:

        1. no outstanding interest references from :meth:`acquire`,
        2. the lock is not currently held,
        3. no waiters are parked on the object.

        Condition 3 matters because ``asyncio.Lock`` reports *unlocked*
        between ``release()`` and the moment a waiter's coroutine resumes;
        pruning in that window would strand the waiter on an orphaned object
        while later arrivals received a fresh lock — silently breaking
        per-session mutual exclusion (audit finding BUG-001).
        """
        if self._refs.get(session_id):
            return
        lock = self._locks.get(session_id)
        if lock is None or lock.locked():
            return
        waiters = getattr(lock, "_waiters", None)
        if waiters:
            return
        self._locks.pop(session_id, None)

    def __getstate__(self) -> dict[str, Any]:
        """Prevent accidental pickling of asyncio locks."""
        raise TypeError("SessionLockManager cannot be pickled")
