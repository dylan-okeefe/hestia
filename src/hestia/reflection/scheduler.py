"""Scheduler integration for the reflection loop."""

from __future__ import annotations

import logging
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from croniter import croniter

from hestia.core.clock import utcnow

if TYPE_CHECKING:
    from hestia.config import ReflectionConfig
    from hestia.persistence.sessions import SessionStore
    from hestia.reflection.runner import ReflectionRunner

logger = logging.getLogger(__name__)


class ReflectionScheduler:
    """Checks whether reflection should run based on cron and idle rules.

    This is not a full scheduler engine; it is a lightweight checker
    intended to be called from the main Scheduler tick loop or daemon.
    """

    def __init__(
        self,
        config: ReflectionConfig,
        runner: ReflectionRunner,
        session_store: SessionStore,
    ) -> None:
        self._config = config
        self._runner = runner
        self._session_store = session_store
        self._last_run_at: datetime | None = None
        self._failure_log: deque[tuple[datetime, str, str, str]] = deque(maxlen=20)
        self.failure_count = 0

    def _record_failure(self, stage: str, exc: Exception) -> None:
        self._failure_log.append(
            (datetime.now(UTC), stage, type(exc).__name__, str(exc)[:200])
        )
        self.failure_count += 1

    def wire_failure_handler(self, runner: ReflectionRunner) -> None:
        """Attach this scheduler's failure recorder to the given runner.

        Keeps ``_record_failure`` private while allowing ``CliAppContext``
        to connect the runner without reaching into our internals.
        """
        runner.set_failure_handler(self._record_failure)

    def status(self) -> dict[str, Any]:
        return {
            "ok": self.failure_count == 0,
            "failure_count": self.failure_count,
            "last_errors": [
                {
                    "timestamp": ts.isoformat(),
                    "stage": stage,
                    "type": exc_type,
                    "message": msg,
                }
                for ts, stage, exc_type, msg in self._failure_log
            ],
            "last_run_at": self._last_run_at,
        }

    async def tick(self, now: datetime | None = None) -> list[Any]:
        """Check if reflection is due and idle, then run if appropriate.

        Returns the list of proposals generated (empty if skipped).
        """
        if now is None:
            now = utcnow()

        if not self._config.enabled:
            return []

        # Check cron: is now a scheduled run time?
        if not self._is_due(now):
            return []

        # Check idle: no session HOT within idle_minutes
        if not await self._is_idle(now):
            logger.info("Reflection skipped: sessions were recently active")
            return []

        self._last_run_at = now
        try:
            proposals = await self._runner.run()
            return proposals
        except Exception as e:  # noqa: BLE001
            self._record_failure("tick", e)
            logger.exception("Reflection run failed: %s", e)
            return []

    def _is_due(self, now: datetime) -> bool:
        """True if the cron expression fires at *now* and we haven't run this minute."""
        try:
            itr = croniter(self._config.cron, now)
            prev_run = itr.get_prev(datetime)
        except Exception as e:  # noqa: BLE001
            logger.warning("Invalid reflection cron '%s': %s", self._config.cron, e)
            return False

        # Only run if we haven't run since this cron slot started
        if self._last_run_at is not None and self._last_run_at >= prev_run:
            return False

        # Ensure now is within one tick interval of the cron slot to avoid
        # double-firing if tick() is called multiple times per minute.
        # We use a 2-minute window.
        return (now - prev_run) <= timedelta(minutes=2)

    async def _is_idle(self, now: datetime) -> bool:
        """True if no session has been active within idle_minutes."""
        # We check the sessions table for any last_active_at within the idle window.
        # This is a best-effort proxy: we don't have a direct HOT/COLD timestamp,
        # but last_active_at on any active session is close enough.
        cutoff = now - timedelta(minutes=self._config.idle_minutes)

        # SessionStore doesn't expose a list_recently_active method, so we
        # query via the underlying database engine directly.
        import sqlalchemy as sa

        from hestia.core.types import SessionState
        from hestia.persistence.schema import sessions

        sql = sa.select(sa.func.count(sessions.c.id)).where(
            sa.and_(
                sessions.c.state == SessionState.ACTIVE.value,
                sessions.c.last_active_at >= cutoff.isoformat(),
            )
        )

        async with self._session_store._db.engine.connect() as conn:
            result = await conn.execute(sql)
            count = result.scalar() or 0

        return count == 0
