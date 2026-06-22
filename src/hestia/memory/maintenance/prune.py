"""Deterministic memory prune maintenance pass."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from hestia.core.clock import utcnow
from hestia.memory.maintenance.trace import MaintenanceAction
from hestia.memory.sanitizer import MemorySanitizer
from hestia.memory.store import Memory, MemoryStore

if TYPE_CHECKING:
    from hestia.persistence.maintenance_trace_store import MaintenanceTraceStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PruneResult:
    """Result of a deterministic prune pass."""

    junk_count: int
    orphan_count: int


class DeterministicPruner:
    """Conservative, unattended prune pass for clear junk and orphans.

    The pruner only soft-deletes memories. It never hard-deletes, and it
    always skips the protected set (pinned, user-authored, recently recalled).
    """

    def __init__(
        self,
        memory_store: MemoryStore,
        sanitizer: MemorySanitizer | None = None,
        trace_store: MaintenanceTraceStore | None = None,
        undo_retention_days: int = 7,
    ) -> None:
        self._store = memory_store
        self._sanitizer = sanitizer or MemorySanitizer()
        self._trace_store = trace_store
        self._undo_retention_days = undo_retention_days

    async def _record_prune(
        self,
        platform: str | None,
        platform_user: str | None,
        memory: Memory,
        reason: str,
    ) -> None:
        """Record a prune action in the trace store, if configured."""
        if self._trace_store is None:
            logger.info(
                "Maintenance prune: %s (%s)",
                memory.id,
                reason,
            )
            return
        now = utcnow()
        action = MaintenanceAction(
            id=f"maint_{uuid.uuid4().hex[:16]}",
            action="prune",
            identity_platform=platform,
            identity_user=platform_user,
            winner_memory_id=None,
            loser_memory_ids=[memory.id],
            reason=reason,
            created_at=now,
            undoable_until=now + timedelta(days=self._undo_retention_days),
            details={},
        )
        try:
            await self._trace_store.record(action)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to record maintenance prune trace")

    async def run(
        self,
        platform: str | None = None,
        platform_user: str | None = None,
    ) -> PruneResult:
        """Run the deterministic prune pass.

        Args:
            platform: Optional platform identifier to scope the pass.
            platform_user: Optional user identifier to scope the pass.

        Returns:
            PruneResult with counts of junk and orphan soft-deletions.
        """
        active = await self._store.list_active_memories(
            platform=platform,
            platform_user=platform_user,
            limit=10_000,
        )

        junk_count = 0
        orphan_count = 0

        for memory in active:
            if self._store.is_protected(memory):
                continue

            if self._is_junk(memory):
                await self._store.soft_delete(
                    memory.id,
                    platform=platform,
                    platform_user=platform_user,
                    reason="junk",
                )
                await self._record_prune(platform, platform_user, memory, "junk")
                junk_count += 1
                continue

            if self._is_orphan(memory):
                await self._store.soft_delete(
                    memory.id,
                    platform=platform,
                    platform_user=platform_user,
                    reason="orphan",
                )
                await self._record_prune(platform, platform_user, memory, "orphan")
                orphan_count += 1

        return PruneResult(junk_count=junk_count, orphan_count=orphan_count)

    def _is_junk(self, memory: Memory) -> bool:
        """Return True when content would be rejected by the write sanitizer."""
        result = self._sanitizer.sanitize(memory.content)
        return result.rejected

    def _is_orphan(self, memory: Memory) -> bool:
        """Return True when a memory is unscoped or effectively empty."""
        return (
            memory.platform is None
            or memory.platform_user is None
            or not memory.content.strip()
        )
