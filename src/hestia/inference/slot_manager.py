"""SlotManager: manages llama.cpp server slot assignment and eviction."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from hestia.core.inference import InferenceClient
from hestia.core.types import Session, SessionTemperature
from hestia.errors import InferenceServerError, PersistenceError
from hestia.persistence.session_store import SessionStore

logger = logging.getLogger(__name__)

_UNSAFE_SLOT_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def _sanitize_slot_filename(session_id: str) -> str:
    """Sanitize a session_id for use in a llama.cpp slot filename.

    llama.cpp's /slots?action=save|restore validator rejects path separators
    AND other characters like `!` and `:`, which appear in Matrix room IDs
    (e.g. `!abc:matrix.org`). Replace anything outside `[A-Za-z0-9._-]` with
    `_`. Session IDs already include a timestamp plus random suffix so
    post-sanitization collisions are negligible in practice.
    """
    return _UNSAFE_SLOT_FILENAME_CHARS.sub("_", session_id)


@dataclass
class SlotAssignment:
    """Result of acquiring a slot for a session."""

    slot_id: int
    restored_from_disk: bool  # True if we called slot_restore


class SlotManager:
    """Maps sessions to llama.cpp server slots with LRU eviction.

    Responsibilities:
      - Assign a live slot to a session for the duration of a turn
      - Save slot state to disk after a turn so it survives eviction/restart
      - Evict the least-recently-used session when the pool is full
      - Restore a WARM session's slot from disk on demand
    """

    def __init__(
        self,
        inference: InferenceClient,
        session_store: SessionStore,
        slot_dir: Path,
        pool_size: int = 4,
    ):
        self._inference = inference
        self._store = session_store
        self._slot_dir = slot_dir
        self._pool_size = pool_size

        # slot_id -> session_id for currently hot sessions
        self._assignments: dict[int, str] = {}
        self._lock = asyncio.Lock()

        self._slot_dir.mkdir(parents=True, exist_ok=True)

    async def acquire(self, session: Session) -> SlotAssignment:
        """Ensure `session` has a live slot. Returns the slot id and whether
        we restored from disk.

        Behavior by session.temperature:
          - HOT: verify slot_id is still assigned to this session, return it
          - WARM: allocate a slot (evicting LRU if needed), restore from disk
          - COLD: allocate a slot, no restore
        """
        async with self._lock:
            if session.temperature == SessionTemperature.HOT:
                if session.slot_id is None:
                    # Inconsistent state — treat as COLD
                    logger.warning(
                        "Session %s marked HOT but slot_id is None; treating as COLD",
                        session.id,
                    )
                    slot_id = await self._allocate_slot(session.id)
                    try:
                        await self._store.assign_slot(session.id, slot_id)
                    except PersistenceError:
                        self._assignments.pop(slot_id, None)
                        raise
                    return SlotAssignment(slot_id=slot_id, restored_from_disk=False)

                # Verify the assignment map agrees
                owner = self._assignments.get(session.slot_id)
                if owner != session.id:
                    # Server restart, or another process stole it; reallocate
                    logger.info(
                        "Session %s thinks it owns slot %d but "
                        "assignment map says %r; reallocating",
                        session.id,
                        session.slot_id,
                        owner,
                    )
                    slot_id = await self._allocate_slot(session.id)
                    try:
                        if session.slot_saved_path:
                            # Derive filename from session.id so save and restore
                            # agree on sanitization; DB value is just a flag that
                            # a snapshot exists.
                            filename = self._slot_path_for(session.id).name
                            await self._inference.slot_restore(slot_id, filename)
                            await self._store.assign_slot(
                                session.id, slot_id, clear_saved_path=True
                            )
                            return SlotAssignment(slot_id=slot_id, restored_from_disk=True)
                        else:
                            await self._store.assign_slot(session.id, slot_id)
                            return SlotAssignment(slot_id=slot_id, restored_from_disk=False)
                    except (PersistenceError, InferenceServerError) as exc:
                        logger.warning(
                            "Slot restore failed for session %s: %s; falling back to fresh slot",
                            session.id,
                            exc,
                        )
                        self._assignments.pop(slot_id, None)
                        # Clear saved path so we don't retry a broken snapshot
                        await self._store.assign_slot(session.id, slot_id)
                        return SlotAssignment(slot_id=slot_id, restored_from_disk=False)

                return SlotAssignment(slot_id=session.slot_id, restored_from_disk=False)

            elif session.temperature == SessionTemperature.WARM:
                slot_id = await self._allocate_slot(session.id)
                try:
                    if session.slot_saved_path is None:
                        logger.warning(
                            "Session %s is WARM but has no slot_saved_path; skipping restore",
                            session.id,
                        )
                        await self._store.assign_slot(session.id, slot_id)
                        return SlotAssignment(slot_id=slot_id, restored_from_disk=False)

                    filename = self._slot_path_for(session.id).name
                    await self._inference.slot_restore(slot_id, filename)
                    await self._store.assign_slot(session.id, slot_id, clear_saved_path=True)
                    return SlotAssignment(slot_id=slot_id, restored_from_disk=True)
                except (OSError, PersistenceError, httpx.HTTPError, RuntimeError, InferenceServerError) as exc:
                    logger.warning(
                        "Slot restore failed for session %s: %s; falling back to fresh slot",
                        session.id,
                        exc,
                    )
                    self._assignments.pop(slot_id, None)
                    # Clear saved path so we don't retry a broken snapshot
                    await self._store.assign_slot(session.id, slot_id)
                    return SlotAssignment(slot_id=slot_id, restored_from_disk=False)

            else:  # COLD
                slot_id = await self._allocate_slot(session.id)
                try:
                    await self._store.assign_slot(session.id, slot_id)
                except (OSError, PersistenceError, httpx.HTTPError, RuntimeError):
                    self._assignments.pop(slot_id, None)
                    raise
                return SlotAssignment(slot_id=slot_id, restored_from_disk=False)

    async def save(self, session: Session) -> None:
        """Save the session's slot state to disk. Call this after each turn
        completes successfully. The slot stays assigned and HOT.
        """
        if session.slot_id is None:
            logger.warning("save() called on session %s with no slot_id", session.id)
            return
        saved_path = self._slot_path_for(session.id)
        try:
            async with self._lock:
                await self._inference.slot_save(session.slot_id, saved_path.name)
        except InferenceServerError as e:
            logger.error(
                "slot_save failed for session %s slot %d: %s",
                session.id,
                session.slot_id,
                e,
            )
            raise
        # Note: we do NOT demote temperature here. Slot is still HOT; this is
        # just a checkpoint. slot_saved_path is updated so eviction knows where to find it.
        await self._store.update_saved_path(session.id, saved_path.name)

    async def erase(self, session: Session) -> None:
        """Erase the session's live slot without saving KV cache to disk.

        Use this when a turn terminates in a non-DONE state and we want to
        discard the in-memory slot state rather than checkpoint a potentially
        corrupted turn.
        """
        if session.slot_id is None:
            logger.warning("erase() called on session %s with no slot_id", session.id)
            return

        async with self._lock:
            self._assignments.pop(session.slot_id, None)
            try:
                await self._inference.slot_erase(session.slot_id)
            except (OSError, InferenceServerError, httpx.HTTPError) as exc:
                logger.warning(
                    "slot_erase failed for session %s slot %d: %s",
                    session.id,
                    session.slot_id,
                    exc,
                )

        await self._store.release_slot(
            session.id,
            demote_to=SessionTemperature.COLD,
            saved_path=None,
        )

    async def evict_by_id(self, session_id: str) -> None:
        """Forcibly evict a specific session from its slot. Saves state to disk first."""
        async with self._lock:
            await self._evict_session_locked(session_id)

    async def _allocate_slot(self, session_id: str) -> int:
        """Find a free slot for session_id, evicting LRU if necessary.

        Caller must hold self._lock.
        """
        # Find a free slot
        for sid in range(self._pool_size):
            if sid not in self._assignments:
                self._assignments[sid] = session_id
                return sid

        # Pool full — evict LRU
        victim_session_id = await self._pick_lru_victim()
        if victim_session_id is None:
            raise RuntimeError("No LRU victim available — slot pool exhausted")
        victim_slot_id = await self._evict_session_locked(victim_session_id)
        # Another coroutine may have taken the freed slot during I/O.
        if victim_slot_id in self._assignments:
            return await self._allocate_slot(session_id)
        self._assignments[victim_slot_id] = session_id
        return victim_slot_id

    async def _evict_session_locked(self, session_id: str) -> int:
        """Save a session's slot to disk and release it. Returns the freed slot id.

        Caller must hold self._lock.
        """
        session = await self._store.get_session(session_id)
        if session is None or session.slot_id is None:
            raise RuntimeError(f"Cannot evict session {session_id}: not assigned to a slot")

        slot_id = session.slot_id
        saved_path = self._slot_path_for(session_id)

        # Remove from assignments BEFORE releasing lock so no other coroutine
        # can pick this same victim while we perform slow I/O.
        del self._assignments[slot_id]

        released = False
        try:
            # Release the lock before slow HTTP I/O so other acquire() calls
            # are not stalled.
            self._lock.release()
            released = True
            await self._inference.slot_save(slot_id, saved_path.name)
            await self._inference.slot_erase(slot_id)
        except Exception as exc:
            # Continue despite I/O error — victim is already excluded from the
            # pool, which prevents the double-eviction race.
            logger.warning(
                "slot_save/slot_erase failed for session %s slot %d: %s",
                session_id,
                slot_id,
                exc,
            )
        finally:
            # Re-acquire the lock if we released it.  We must always hold the
            # lock on exit so callers can safely update _assignments.
            if released:
                await self._lock.acquire()

        # Lock is held again — update state.
        await self._store.release_slot(
            session_id,
            demote_to=SessionTemperature.WARM,
            saved_path=saved_path.name,
        )
        logger.info("Evicted session %s from slot %d", session_id, slot_id)
        return slot_id

    async def _pick_lru_victim(self) -> str | None:
        """Pick the assigned session with the oldest last_active_at. Returns session_id."""
        candidates = list(self._assignments.values())
        if not candidates:
            return None
        # Load all candidates in a single query instead of N serial round-trips.
        session_map = await self._store.get_sessions_batch(candidates)
        if not session_map:
            return None
        session_list = sorted(session_map.values(), key=lambda s: s.last_active_at)
        return session_list[0].id

    def _slot_path_for(self, session_id: str) -> Path:
        return self._slot_dir / f"{_sanitize_slot_filename(session_id)}.bin"
