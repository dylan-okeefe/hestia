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
    platform: str
    platform_user: str
    metric: str
    value_json: str
    updated_at: datetime
class StyleProfileStore:
    """Store for style profile metrics."""
    def __init__(self, db: Database) -> None:
        self._db = db
    async def create_table(self) -> None:
        ddl = "CREATE TABLE IF NOT EXISTS style_profiles (platform TEXT NOT NULL, platform_user TEXT NOT NULL, metric TEXT NOT NULL, value_json TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY (platform, platform_user, metric))"  # noqa: E501
        async with self._db.engine.connect() as conn:
            await conn.execute(sa.text(ddl))
            for idx in ("CREATE INDEX IF NOT EXISTS idx_style_profiles_user ON style_profiles(platform, platform_user)", "CREATE INDEX IF NOT EXISTS idx_style_profiles_updated ON style_profiles(updated_at)"):  # noqa: E501
                await conn.execute(sa.text(idx))
            await conn.commit()
    async def get_metric(self, platform: str, platform_user: str, metric: str) -> StyleMetric | None:  # noqa: E501
        sql = sa.text("SELECT platform, platform_user, metric, value_json, updated_at FROM style_profiles WHERE platform = :platform AND platform_user = :platform_user AND metric = :metric")  # noqa: E501
        async with self._db.engine.connect() as conn:
            row = (await conn.execute(sql, {"platform": platform, "platform_user": platform_user, "metric": metric})).fetchone()  # noqa: E501
            return self._row_to_metric(row) if row else None
    async def set_metric(self, platform: str, platform_user: str, metric: str, value: Any) -> None:
        sql = sa.text("INSERT INTO style_profiles (platform, platform_user, metric, value_json, updated_at) VALUES (:platform, :platform_user, :metric, :value_json, :updated_at) ON CONFLICT (platform, platform_user, metric) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at")  # noqa: E501
        async with self._db.engine.connect() as conn:
            await conn.execute(sql, {
                "platform": platform, "platform_user": platform_user, "metric": metric,
                "value_json": json.dumps(value), "updated_at": utcnow().isoformat(),
            })
            await conn.commit()
    async def list_metrics(self, platform: str, platform_user: str) -> list[StyleMetric]:
        sql = sa.text("SELECT platform, platform_user, metric, value_json, updated_at FROM style_profiles WHERE platform = :platform AND platform_user = :platform_user")  # noqa: E501
        async with self._db.engine.connect() as conn:
            return [self._row_to_metric(r) for r in (await conn.execute(sql, {"platform": platform, "platform_user": platform_user})).fetchall()]  # noqa: E501
    async def delete_profile(self, platform: str, platform_user: str) -> int:
        sql = sa.text("DELETE FROM style_profiles WHERE platform = :platform AND platform_user = :platform_user")  # noqa: E501
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"platform": platform, "platform_user": platform_user})
            await conn.commit()
            return result.rowcount or 0
    async def count_turns_in_window(self, platform: str, platform_user: str, since: datetime) -> int:  # noqa: E501
        sql = sa.text("SELECT COUNT(*) FROM turns t JOIN sessions s ON t.session_id = s.id WHERE s.platform = :platform AND s.platform_user = :platform_user AND t.started_at >= :since")  # noqa: E501
        async with self._db.engine.connect() as conn:
            return (await conn.execute(sql, {"platform": platform, "platform_user": platform_user, "since": since.isoformat()})).scalar() or 0  # noqa: E501
    async def get_profile_dict(self, platform: str, platform_user: str) -> dict[str, Any]:
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
            platform=row.platform, platform_user=row.platform_user,
            metric=row.metric, value_json=row.value_json, updated_at=updated_at,
        )
