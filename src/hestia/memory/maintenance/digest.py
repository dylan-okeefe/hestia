"""Memory maintenance digest assembler and delivery."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hestia.core.clock import utcnow
from hestia.core.types import ScheduledTask
from hestia.memory.maintenance.trace import MaintenanceAction

if TYPE_CHECKING:
    from hestia.persistence.maintenance_trace_store import MaintenanceTraceStore
    from hestia.persistence.session_store import SessionStore
    from hestia.platforms.notifier import PlatformNotifier

logger = logging.getLogger(__name__)


class MemoryMaintenanceDigest:
    """Assemble and deliver a digest of recent memory maintenance actions."""

    def __init__(
        self,
        trace_store: MaintenanceTraceStore,
        session_store: SessionStore | None = None,
        notifier: PlatformNotifier | None = None,
    ) -> None:
        self._trace_store = trace_store
        self._session_store = session_store
        self._notifier = notifier

    async def query(
        self,
        since: datetime | None = None,
        *,
        platform: str | None = None,
        platform_user: str | None = None,
        limit: int = 1000,
    ) -> list[MaintenanceAction]:
        """Return maintenance actions since *since* (default 24h)."""
        if since is None:
            since = utcnow() - timedelta(days=1)
        return await self._trace_store.list_recent(
            platform=platform,
            platform_user=platform_user,
            since=since,
            limit=limit,
        )

    def format_digest(
        self,
        actions: Sequence[MaintenanceAction],
        *,
        title: str = "Memory maintenance digest",
    ) -> str | None:
        """Format actions into a human-readable summary.

        Returns ``None`` when there are no actions.
        """
        if not actions:
            return None

        merges = [a for a in actions if a.action == "merge"]
        prunes = [a for a in actions if a.action == "prune"]
        supersedes = [a for a in actions if a.action == "supersede"]
        undos = [a for a in actions if a.action == "undo"]

        lines: list[str] = [f"**{title}**"]
        lines.append(f"Total actions: {len(actions)}")

        if supersedes:
            lines.append("")
            lines.append(f"⚠️ Supersessions ({len(supersedes)}) — review recommended:")
            for action in supersedes:
                winner = action.winner_memory_id or "unknown"
                losers = ", ".join(action.loser_memory_ids) or "unknown"
                attribute = action.details.get("attribute") or "unknown"
                lines.append(
                    f"  • {losers} superseded by {winner} on '{attribute}'"
                )

        if merges:
            lines.append("")
            lines.append(f"🔄 Merges ({len(merges)}):")
            merge_groups: dict[str, list[MaintenanceAction]] = {}
            for action in merges:
                key = action.details.get("phase", "other")
                merge_groups.setdefault(key, []).append(action)
            for phase, phase_actions in sorted(merge_groups.items()):
                label = "exact duplicate" if phase == "exact" else phase
                lines.append(f"  {label} ({len(phase_actions)})")

        if prunes:
            lines.append("")
            lines.append(f"🗑️ Prunes ({len(prunes)}):")
            prune_counts: dict[str, int] = {}
            for action in prunes:
                prune_counts[action.reason] = prune_counts.get(action.reason, 0) + 1
            for reason, count in sorted(prune_counts.items()):
                lines.append(f"  {reason}: {count}")

        if undos:
            lines.append("")
            lines.append(f"↩️ Undos ({len(undos)})")

        # Undo deadline: the soonest undoable_until among reported actions.
        soonest_deadline = min(a.undoable_until for a in actions)
        lines.append("")
        lines.append(f"Undo deadline: {soonest_deadline.isoformat()}")

        return "\n".join(lines)

    async def send_digest(
        self,
        *,
        since: datetime | None = None,
        session_id: str | None = None,
        title: str = "Memory maintenance digest",
        platform: str | None = None,
        platform_user: str | None = None,
    ) -> str:
        """Assemble the digest and optionally push it to the operator.

        Returns the formatted digest text, or ``"SILENT"`` when there are no
        actions so scheduled-task delivery can skip empty messages.
        """
        actions = await self.query(
            since=since,
            platform=platform,
            platform_user=platform_user,
        )
        text = self.format_digest(actions, title=title)
        if text is None:
            return "SILENT"

        if self._notifier is not None and session_id is not None:
            await self._notify(session_id, text)

        return text

    async def send_digest_for_task(self, task: ScheduledTask) -> str:
        """Assemble a digest for a scheduled task.

        The window is ``task.last_run_at`` (or ``task.created_at`` for the
        first run) to now.
        """
        since = task.last_run_at or task.created_at
        return await self.send_digest(
            since=since,
            session_id=task.session_id,
            title="Scheduled memory maintenance digest",
        )

    async def _notify(self, session_id: str, text: str) -> None:
        if self._session_store is None or self._notifier is None:
            return
        try:
            session = await self._session_store.get_session(session_id)
            if session is None:
                return
            await self._notifier.send(
                session.platform, session.platform_user, text
            )
        except Exception as exc:  # noqa: BLE001 — notification must not crash digest
            logger.warning("Failed to send memory maintenance digest: %s", exc)
