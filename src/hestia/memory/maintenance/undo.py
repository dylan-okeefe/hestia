"""Undo support for memory maintenance actions.

Within the undo window an operator can restore the memories that were
soft-deleted by a merge, prune, or supersede action. Each undo is itself
recorded in the maintenance trace so the audit log remains complete.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from hestia.core.clock import utcnow
from hestia.memory.maintenance.trace import MaintenanceAction

if TYPE_CHECKING:
    from hestia.memory.store import MemoryStore
    from hestia.persistence.maintenance_trace_store import MaintenanceTraceStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UndoResult:
    """Result of attempting to undo a maintenance action."""

    action_id: str
    restored_count: int
    undo_action_id: str


class MaintenanceUndo:
    """Restore memories soft-deleted by a maintenance action."""

    def __init__(
        self,
        memory_store: MemoryStore,
        trace_store: MaintenanceTraceStore,
        *,
        undo_retention_days: int = 7,
    ) -> None:
        self._memory_store = memory_store
        self._trace_store = trace_store
        self._undo_retention_days = undo_retention_days

    async def undo(self, action_id: str) -> UndoResult:
        """Undo a maintenance action by restoring its loser memories.

        Args:
            action_id: The maintenance action to undo.

        Returns:
            UndoResult describing how many memories were restored.

        Raises:
            ValueError: If the action does not exist or is outside the undo window.
        """
        action = await self._trace_store.get(action_id)
        if action is None:
            raise ValueError(f"Maintenance action not found: {action_id}")

        if action.action == "undo":
            raise ValueError(f"Action {action_id} is itself an undo; undo it directly")

        now = utcnow()
        if now > action.undoable_until:
            raise ValueError(
                f"Action {action_id} is outside the undo window "
                f"(deadline was {action.undoable_until.isoformat()})"
            )

        restored_count = 0
        for memory_id in action.loser_memory_ids:
            if await self._memory_store.restore(
                memory_id,
                platform=action.identity_platform,
                platform_user=action.identity_user,
            ):
                restored_count += 1
            else:
                logger.warning(
                    "Undo for action %s could not restore memory %s "
                    "(already active or missing)",
                    action_id,
                    memory_id,
                )

        undo_action = MaintenanceAction(
            id=f"maint_{uuid.uuid4().hex[:16]}",
            action="undo",
            identity_platform=action.identity_platform,
            identity_user=action.identity_user,
            winner_memory_id=None,
            loser_memory_ids=list(action.loser_memory_ids),
            reason=f"undo of {action_id}",
            created_at=now,
            undoable_until=now + timedelta(days=self._undo_retention_days),
            details={"undone_action_id": action_id, "restored_count": restored_count},
        )
        await self._trace_store.record(undo_action)

        return UndoResult(
            action_id=action_id,
            restored_count=restored_count,
            undo_action_id=undo_action.id,
        )
