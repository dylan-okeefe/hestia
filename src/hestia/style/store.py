"""Persistence layer for style profile metrics."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa

from hestia.core.clock import utcnow
from hestia.persistence.db import Database


@dataclass
class StyleMetric:
    """A single metric row for a user."""

    platform: str
    platform_user: str
    metric: str
    value_json: str
    updated_at: datetime


class StyleProfileStore:
    """Store for style profile metrics.

    Uses raw DDL for table creation (consistent with TraceStore pattern).
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create_table(self) -> None:
        """Create the style_profiles table if it doesn't exist."""
        ddl = """
        CREATE TABLE IF NOT EXISTS style_profiles (
            platform TEXT NOT NULL,
            platform_user TEXT NOT NULL,
            metric TEXT NOT NULL,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (platform, platform_user, metric)
        )
        """
        idx_user = (
            "CREATE INDEX IF NOT EXISTS idx_style_profiles_user "
            "ON style_profiles(platform, platform_user)"
        )
        idx_updated = (
            "CREATE INDEX IF NOT EXISTS idx_style_profiles_updated "
            "ON style_profiles(updated_at)"
        )

        async with self._db.engine.connect() as conn:
            await conn.execute(sa.text(ddl))
            await conn.execute(sa.text(idx_user))
            await conn.execute(sa.text(idx_updated))
            await conn.commit()

    async def get_metric(
        self, platform: str, platform_user: str, metric: str
    ) -> StyleMetric | None:
        """Fetch a single metric for a user."""
        sql = sa.text(
            "SELECT platform, platform_user, metric, value_json, updated_at "
            "FROM style_profiles WHERE platform = :platform AND platform_user = :platform_user "
            "AND metric = :metric"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(
                sql, {"platform": platform, "platform_user": platform_user, "metric": metric}
            )
            row = result.fetchone()
            if row is None:
                return None
            return self._row_to_metric(row)

    async def set_metric(
        self,
        platform: str,
        platform_user: str,
        metric: str,
        value: Any,
    ) -> None:
        """Upsert a metric value (serialized as JSON)."""
        value_json = json.dumps(value)
        now = utcnow().isoformat()
        sql = sa.text(
            "INSERT INTO style_profiles (platform, platform_user, metric, value_json, updated_at) "
            "VALUES (:platform, :platform_user, :metric, :value_json, :updated_at) "
            "ON CONFLICT (platform, platform_user, metric) DO UPDATE SET "
            "value_json = excluded.value_json, updated_at = excluded.updated_at"
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(
                sql,
                {
                    "platform": platform,
                    "platform_user": platform_user,
                    "metric": metric,
                    "value_json": value_json,
                    "updated_at": now,
                },
            )
            await conn.commit()

    async def list_metrics(self, platform: str, platform_user: str) -> list[StyleMetric]:
        """List all metrics for a user."""
        sql = sa.text(
            "SELECT platform, platform_user, metric, value_json, updated_at "
            "FROM style_profiles WHERE platform = :platform AND platform_user = :platform_user"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(
                sql, {"platform": platform, "platform_user": platform_user}
            )
            rows = result.fetchall()
            return [self._row_to_metric(row) for row in rows]

    async def delete_profile(self, platform: str, platform_user: str) -> int:
        """Delete all metrics for a user. Returns row count."""
        sql = sa.text(
            "DELETE FROM style_profiles WHERE platform = :platform AND platform_user = :platform_user"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(
                sql, {"platform": platform, "platform_user": platform_user}
            )
            await conn.commit()
            return result.rowcount or 0

    async def count_turns_in_window(
        self, platform: str, platform_user: str, since: datetime
    ) -> int:
        """Count turns for this user since a given time."""
        sql = sa.text(
            "SELECT COUNT(*) FROM turns t "
            "JOIN sessions s ON t.session_id = s.id "
            "WHERE s.platform = :platform AND s.platform_user = :platform_user "
            "AND t.started_at >= :since"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(
                sql,
                {
                    "platform": platform,
                    "platform_user": platform_user,
                    "since": since.isoformat(),
                },
            )
            return result.scalar() or 0

    async def get_profile_dict(
        self, platform: str, platform_user: str
    ) -> dict[str, Any]:
        """Return all metrics for a user as a plain dict."""
        metrics = await self.list_metrics(platform, platform_user)
        result: dict[str, Any] = {}
        for m in metrics:
            try:
                result[m.metric] = json.loads(m.value_json)
            except json.JSONDecodeError:
                result[m.metric] = m.value_json
        return result

    def _row_to_metric(self, row: Any) -> StyleMetric:
        updated_at = row.updated_at
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        return StyleMetric(
            platform=row.platform,
            platform_user=row.platform_user,
            metric=row.metric,
            value_json=row.value_json,
            updated_at=updated_at,
        )
