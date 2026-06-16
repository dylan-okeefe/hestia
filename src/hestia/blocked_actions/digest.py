"""Blocked-actions digest: assemble and deliver CapabilityGate audit summaries."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hestia.core.clock import utcnow
from hestia.core.types import ScheduledTask
from hestia.persistence.scheduler import SchedulerStore

if TYPE_CHECKING:
    from hestia.persistence.capability_events import CapabilityEvent, CapabilityEventStore
    from hestia.persistence.session_store import SessionStore
    from hestia.platforms.notifier import PlatformNotifier

logger = logging.getLogger(__name__)


class BlockedActionsDigest:
    """Read-only assembler for the blocked-actions digest.

    The digest pulls deny/escalate records from ``CapabilityEventStore``,
    formats them for the operator, and can push the result through the
    existing ``PlatformNotifier``.
    """

    def __init__(
        self,
        event_store: CapabilityEventStore,
        session_store: SessionStore | None = None,
        notifier: PlatformNotifier | None = None,
    ) -> None:
        self._event_store = event_store
        self._session_store = session_store
        self._notifier = notifier

    async def query(
        self,
        since: datetime | None = None,
        *,
        limit: int = 1000,
    ) -> list[CapabilityEvent]:
        """Return blocked/escalated events since *since* (default 24h)."""
        if since is None:
            since = utcnow() - timedelta(days=1)
        return await self._event_store.list_since(since, limit=limit)

    def format_digest(
        self,
        events: Sequence[CapabilityEvent],
        *,
        title: str = "Blocked actions digest",
    ) -> str | None:
        """Format events into a human-readable summary.

        Returns ``None`` when there are no events (so the caller can skip
        sending an empty digest).
        """
        if not events:
            return None

        injection_events = [e for e in events if e.injection_flagged]
        other_events = [e for e in events if not e.injection_flagged]

        lines: list[str] = [f"**{title}**"]
        lines.append(f"Total: {len(events)} blocked/escalated action(s)")

        if injection_events:
            lines.append("")
            lines.append(f"⚠️ Injection-flagged ({len(injection_events)}):")
            for event in injection_events:
                lines.append(self._format_event_line(event))

        if other_events:
            lines.append("")
            grouped = defaultdict(list)
            for event in other_events:
                grouped[self._origin(event)].append(event)
            for origin, origin_events in sorted(grouped.items()):
                lines.append(f"📦 {origin} ({len(origin_events)}):")
                for event in origin_events:
                    lines.append(self._format_event_line(event))

        return "\n".join(lines)

    async def send_digest(
        self,
        *,
        since: datetime | None = None,
        session_id: str | None = None,
        title: str = "Blocked actions digest",
    ) -> str:
        """Assemble the digest and optionally push it to the operator.

        Returns the formatted digest text, or ``"SILENT"`` when there are no
        events so scheduled-task delivery can skip empty messages.
        """
        events = await self.query(since=since)
        text = self.format_digest(events, title=title)
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
            title="Scheduled blocked-actions digest",
        )

    def _format_event_line(self, event: CapabilityEvent) -> str:
        args = ""
        if event.arguments_json:
            try:
                parsed = json.loads(event.arguments_json)
                if parsed:
                    summary = json.dumps(parsed, ensure_ascii=False)
                    if len(summary) > 120:
                        summary = summary[:117] + "..."
                    args = f" — {summary}"
            except json.JSONDecodeError:
                pass
        resolution = "escalated" if event.decision == "escalated" else "denied"
        return (
            f"  • {event.tool_name} ({event.channel}) "
            f"[{resolution}; {event.reason}]{args}"
        )

    def _origin(self, event: CapabilityEvent) -> str:
        if event.source_workflow_id:
            return f"workflow:{event.source_workflow_id}"
        if event.source_trigger_id:
            return f"trigger:{event.source_trigger_id}"
        return f"channel:{event.channel}"

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
            logger.warning("Failed to send blocked-actions digest: %s", exc)


def digest_cron_from_time(time_str: str) -> str:
    """Convert ``HH:MM`` to a daily cron expression."""
    try:
        hour, minute = time_str.split(":")
        return f"{int(minute)} {int(hour)} * * *"
    except ValueError as exc:
        raise ValueError(f"Invalid blocked_digest_time format: {time_str!r}") from exc


async def ensure_blocked_digest_task(
    scheduler_store: SchedulerStore,
    session_id: str,
    time_str: str = "09:00",
) -> ScheduledTask:
    """Create or replace the daily blocked-actions digest scheduled task."""
    cron = digest_cron_from_time(time_str)
    existing = await scheduler_store.list_tasks_for_session(session_id)
    for task in existing:
        if task.task_type == "blocked_digest":
            updated = await scheduler_store.update_task(
                task.id,
                cron_expression=cron,
                enabled=True,
            )
            if updated is not None:
                return updated
    return await scheduler_store.create_task(
        session_id=session_id,
        prompt="blocked-actions digest",
        description="Daily digest of denied/escalated actions",
        cron_expression=cron,
        notify=True,
        task_type="blocked_digest",
    )
