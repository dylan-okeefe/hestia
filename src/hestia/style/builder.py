"""StyleProfileBuilder recomputes interaction-style metrics from traces."""
from __future__ import annotations

import re
import statistics
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import sqlalchemy as sa

from hestia.core.clock import utcnow
from hestia.style.vocab import TECHNICAL_VOCABULARY

if TYPE_CHECKING:
    from hestia.config import StyleConfig
    from hestia.persistence.db import Database
    from hestia.style.store import StyleProfileStore
_WORD_RE = re.compile(r"[a-zA-Z]+")
class StyleProfileBuilder:
    """Recomputes style metrics per platform × user from the last N days."""
    def __init__(self, db: Database, store: StyleProfileStore, config: StyleConfig) -> None:
        self._db = db
        self._store = store
        self._config = config
    async def build_all(self) -> None:
        since = utcnow() - timedelta(days=self._config.lookback_days)
        users = await self._active_users(since)
        for platform, platform_user in users:
            await self._build_one(platform, platform_user, since)
    async def _active_users(self, since: datetime) -> list[tuple[str, str]]:
        sql = sa.text("SELECT DISTINCT platform, platform_user FROM sessions WHERE last_active_at >= :since")  # noqa: E501
        async with self._db.engine.connect() as conn:
            rows = (await conn.execute(sql, {"since": since.isoformat()})).fetchall()
            return [(r.platform, r.platform_user) for r in rows]
    async def _build_one(self, platform: str, platform_user: str, since: datetime) -> None:
        preferred_length = await self._compute_preferred_length(platform, platform_user, since)
        formality = await self._compute_formality(platform, platform_user, since)
        top_topics = await self._compute_top_topics(platform, platform_user, since)
        activity_window = await self._compute_activity_window(platform, platform_user, since)
        if preferred_length is not None:
            await self._store.set_metric(platform, platform_user, "preferred_length", preferred_length)  # noqa: E501
        await self._store.set_metric(platform, platform_user, "formality", formality)
        await self._store.set_metric(platform, platform_user, "top_topics", top_topics)
        await self._store.set_metric(platform, platform_user, "activity_window", activity_window)
    async def _compute_preferred_length(self, platform: str, platform_user: str, since: datetime) -> int | None:  # noqa: E501
        sql = sa.text("SELECT t.session_id, t.started_at, t.completion_tokens FROM traces t JOIN sessions s ON t.session_id = s.id WHERE s.platform = :platform AND s.platform_user = :platform_user AND t.started_at >= :since AND t.completion_tokens IS NOT NULL")  # noqa: E501
        async with self._db.engine.connect() as conn:
            traces = (await conn.execute(sql, {"platform": platform, "platform_user": platform_user, "since": since.isoformat()})).fetchall()  # noqa: E501
        if not traces:
            return None
        values: list[int] = []
        for row in traces:
            if row.completion_tokens is None:
                continue
            if not await self._has_length_feedback(row.session_id, row.started_at):
                values.append(row.completion_tokens)
        return int(statistics.median(values)) if values else None
    async def _has_length_feedback(self, session_id: str, after: datetime | str) -> bool:
        after_str = after.isoformat() if isinstance(after, datetime) else after
        sql = sa.text("SELECT content FROM messages WHERE session_id = :session_id AND role = 'user' AND created_at > :after ORDER BY created_at ASC LIMIT 2")  # noqa: E501
        async with self._db.engine.connect() as conn:
            rows = (await conn.execute(sql, {"session_id": session_id, "after": after_str})).fetchall()  # noqa: E501
        for row in rows:
            text = (row.content or "").lower()
            if "shorter" in text or "longer" in text:
                return True
        return False
    async def _compute_formality(self, platform: str, platform_user: str, since: datetime) -> float:
        sql = sa.text("SELECT m.content FROM messages m JOIN sessions s ON m.session_id = s.id WHERE s.platform = :platform AND s.platform_user = :platform_user AND m.role = 'user' AND m.created_at >= :since")  # noqa: E501
        async with self._db.engine.connect() as conn:
            rows = (await conn.execute(sql, {"platform": platform, "platform_user": platform_user, "since": since.isoformat()})).fetchall()  # noqa: E501
        total_words = 0
        tech_words = 0
        for row in rows:
            words = _WORD_RE.findall((row.content or "").lower())
            total_words += len(words)
            tech_words += sum(1 for w in words if w in TECHNICAL_VOCABULARY)
        return round(tech_words / total_words, 4) if total_words else 0.0
    async def _compute_top_topics(self, platform: str, platform_user: str, since: datetime) -> list[str]:  # noqa: E501
        sql = sa.text("SELECT m.tags FROM memory m JOIN sessions s ON m.session_id = s.id WHERE s.platform = :platform AND s.platform_user = :platform_user AND m.created_at >= :since")  # noqa: E501
        async with self._db.engine.connect() as conn:
            rows = (await conn.execute(sql, {"platform": platform, "platform_user": platform_user, "since": since.isoformat()})).fetchall()  # noqa: E501
        tag_counts: dict[str, int] = {}
        for row in rows:
            raw = row.tags or ""
            if not raw:
                continue
            for tag in (raw.split("|") if "|" in raw else raw.split()):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        return [tag for tag, _ in sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))[:5]]
    async def _compute_activity_window(self, platform: str, platform_user: str, since: datetime) -> list[int]:  # noqa: E501
        sql = sa.text("SELECT t.started_at FROM turns t JOIN sessions s ON t.session_id = s.id WHERE s.platform = :platform AND s.platform_user = :platform_user AND t.started_at >= :since")  # noqa: E501
        async with self._db.engine.connect() as conn:
            rows = (await conn.execute(sql, {"platform": platform, "platform_user": platform_user, "since": since.isoformat()})).fetchall()  # noqa: E501
        histogram = [0] * 24
        for row in rows:
            started_at = datetime.fromisoformat(row.started_at) if isinstance(row.started_at, str) else row.started_at  # noqa: E501
            histogram[started_at.hour] += 1
        return histogram
