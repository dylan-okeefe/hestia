"""Job alert queue store for workflow batching."""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa

from hestia.core.clock import utcnow
from hestia.errors import PersistenceError
from hestia.persistence.db import Database


class JobAlertStore:
    """CRUD for the job_alerts queue table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create_table(self) -> None:
        """Create the job_alerts table if it does not exist."""
        from hestia.persistence.schema import job_alerts

        if self._db.engine is None:
            raise PersistenceError("Database not connected")
        async with self._db.engine.begin() as conn:
            await conn.run_sync(job_alerts.create, checkfirst=True)

    async def save_alert(
        self,
        source_email: str,
        subject: str,
        title: str = "",
        company: str = "",
        location: str = "",
        remote: str = "",
        match_score: int | None = None,
        salary: str = "",
        tech_stack: str = "",
        url: str = "",
        summary: str = "",
    ) -> str:
        """Insert a new job alert and return its id."""
        from hestia.persistence.schema import job_alerts

        alert_id = str(uuid.uuid4())
        now = utcnow()
        async with self._db.engine.begin() as conn:
            await conn.execute(
                sa.insert(job_alerts).values(
                    id=alert_id,
                    created_at=now,
                    source_email=source_email,
                    subject=subject,
                    title=title,
                    company=company,
                    location=location,
                    remote=remote,
                    match_score=match_score,
                    salary=salary,
                    tech_stack=tech_stack,
                    url=url,
                    summary=summary,
                    digest_sent=False,
                )
            )
        return alert_id

    async def list_pending(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return pending alerts (digest_sent=False), newest first."""
        from hestia.persistence.schema import job_alerts

        async with self._db.engine.connect() as conn:
            result = await conn.execute(
                sa.select(job_alerts)
                .where(job_alerts.c.digest_sent.is_(False))
                .order_by(job_alerts.c.created_at.desc())
                .limit(limit)
            )
            rows = result.fetchall()
            return [dict(row._mapping) for row in rows]

    async def mark_all_sent(self) -> int:
        """Mark all pending alerts as sent. Returns row count."""
        from hestia.persistence.schema import job_alerts

        async with self._db.engine.begin() as conn:
            result = await conn.execute(
                sa.update(job_alerts)
                .where(job_alerts.c.digest_sent.is_(False))
                .values(digest_sent=True)
            )
            return result.rowcount or 0

    async def delete_alert(self, alert_id: str) -> bool:
        """Delete a single alert by id. Returns True if deleted."""
        from hestia.persistence.schema import job_alerts

        async with self._db.engine.begin() as conn:
            result = await conn.execute(
                sa.delete(job_alerts).where(job_alerts.c.id == alert_id)
            )
            return (result.rowcount or 0) > 0
