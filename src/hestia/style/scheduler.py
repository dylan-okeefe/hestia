"""Scheduler integration for the style profile builder."""
from __future__ import annotations

import logging
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from croniter import croniter

from hestia.core.clock import utcnow
from hestia.core.types import SessionState
from hestia.persistence.schema import sessions

if TYPE_CHECKING:
    from hestia.config import StyleConfig
    from hestia.persistence.sessions import SessionStore
    from hestia.style.builder import StyleProfileBuilder
logger = logging.getLogger(__name__)
class StyleScheduler:
    """Checks whether the style profile builder should run based on cron + idle rules."""
    def __init__(
        self,
        config: StyleConfig,
        builder: StyleProfileBuilder,
        session_store: SessionStore,
    ) -> None:
        self._config = config
        self._builder = builder
        self._session_store = session_store
        self._last_run_at: datetime | None = None
        self._failure_log: deque[tuple[datetime, str, str, str]] = deque(maxlen=20)
        self.failure_count = 0
    def _record_failure(self, stage: str, exc: Exception) -> None:
        self._failure_log.append((datetime.now(UTC), stage, type(exc).__name__, str(exc)[:200]))
        self.failure_count += 1
    def status(self) -> dict[str, Any]:
        return {
            "ok": self.failure_count == 0,
            "failure_count": self.failure_count,
            "last_errors": [
                {"timestamp": ts.isoformat(), "stage": stage, "type": exc_type, "message": msg}
                for ts, stage, exc_type, msg in self._failure_log
            ],
            "last_run_at": self._last_run_at,
        }
    async def tick(self, now: datetime | None = None) -> None:
        if now is None:
            now = utcnow()
        if not self._config.enabled or not self._is_due(now) or not await self._is_idle(now):
            return
        self._last_run_at = now
        try:
            await self._builder.build_all()
            logger.info("Style profile rebuild complete")
        except Exception as e:  # noqa: BLE001
            self._record_failure("build", e)
            logger.exception("Style profile rebuild failed: %s", e)
    def _is_due(self, now: datetime) -> bool:
        try:
            prev_run = croniter(self._config.cron, now).get_prev(datetime)
        except Exception as e:  # noqa: BLE001
            logger.warning("Invalid style cron '%s': %s", self._config.cron, e)
            return False
        if self._last_run_at is not None and self._last_run_at >= prev_run:
            return False
        return (now - prev_run) <= timedelta(minutes=2)
    async def _is_idle(self, now: datetime) -> bool:
        cutoff = now - timedelta(minutes=15)
        import sqlalchemy as sa
        sql = sa.select(sa.func.count(sessions.c.id)).where(
            sa.and_(
                sessions.c.state == SessionState.ACTIVE.value,
                sessions.c.last_active_at >= cutoff.isoformat(),
            )
        )
        async with self._session_store._db.engine.connect() as conn:
            return (await conn.execute(sql)).scalar() == 0
