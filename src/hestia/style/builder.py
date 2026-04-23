"""StyleProfileBuilder recomputes interaction-style metrics from traces."""

from __future__ import annotations

import re
import statistics
from datetime import datetime, timedelta

import sqlalchemy as sa

from hestia.config import StyleConfig
from hestia.core.clock import utcnow
from hestia.persistence.db import Database
from hestia.style.store import StyleProfileStore
from hestia.style.vocab import TECHNICAL_VOCABULARY

_WORD_RE = re.compile(r"[a-zA-Z]+")


class StyleProfileBuilder:
    """Recomputes style metrics per platform × user from the last N days."""

    def __init__(self, db: Database, store: StyleProfileStore, config: StyleConfig) -> None:
        self._db = db
        self._store = store
        self._config = config

    async def build_all(self) -> None:
        """Recompute style profiles for every active user in the lookback window."""
        since = utcnow() - timedelta(days=self._config.lookback_days)
        users = await self._active_users(since)
        for platform, platform_user in users:
            await self._build_one(platform, platform_user, since)

    async def _active_users(self, since: datetime) -> list[tuple[str, str]]:
        """Return distinct (platform, platform_user) with sessions since `since`."""
        sql = sa.text(
            "SELECT DISTINCT platform, platform_user FROM sessions "
            "WHERE last_active_at >= :since"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"since": since.isoformat()})
            rows = result.fetchall()
            return [(row.platform, row.platform_user) for row in rows]

    async def _build_one(
        self, platform: str, platform_user: str, since: datetime
    ) -> None:
        """Compute and persist the four metrics for a single user."""
        preferred_length = await self._compute_preferred_length(
            platform, platform_user, since
        )
        formality = await self._compute_formality(platform, platform_user, since)
        top_topics = await self._compute_top_topics(platform, platform_user, since)
        activity_window = await self._compute_activity_window(
            platform, platform_user, since
        )

        if preferred_length is not None:
            await self._store.set_metric(
                platform, platform_user, "preferred_length", preferred_length
            )
        await self._store.set_metric(
            platform, platform_user, "formality", formality
        )
        await self._store.set_metric(
            platform, platform_user, "top_topics", top_topics
        )
        await self._store.set_metric(
            platform, platform_user, "activity_window", activity_window
        )

    async def _compute_preferred_length(
        self, platform: str, platform_user: str, since: datetime
    ) -> int | None:
        """Median completion tokens for turns not followed by length feedback."""
        # Fetch traces with completion tokens for this user in window
        sql = sa.text(
            "SELECT t.id, t.turn_id, t.session_id, t.started_at, t.completion_tokens "
            "FROM traces t "
            "JOIN sessions s ON t.session_id = s.id "
            "WHERE s.platform = :platform AND s.platform_user = :platform_user "
            "AND t.started_at >= :since AND t.completion_tokens IS NOT NULL"
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
            traces = result.fetchall()

        if not traces:
            return None

        values: list[int] = []
        for row in traces:
            if row.completion_tokens is None:
                continue
            feedback = await self._has_length_feedback(
                row.session_id, row.started_at
            )
            if not feedback:
                values.append(row.completion_tokens)

        if not values:
            return None
        return int(statistics.median(values))

    async def _has_length_feedback(
        self, session_id: str, after: datetime | str
    ) -> bool:
        """True if any of the next 2 user messages contain 'shorter' or 'longer'."""
        after_str = after.isoformat() if isinstance(after, datetime) else after
        sql = sa.text(
            "SELECT content FROM messages "
            "WHERE session_id = :session_id AND role = 'user' AND created_at > :after "
            "ORDER BY created_at ASC LIMIT 2"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(
                sql, {"session_id": session_id, "after": after_str}
            )
            rows = result.fetchall()
        for row in rows:
            text = (row.content or "").lower()
            if "shorter" in text or "longer" in text:
                return True
        return False

    async def _compute_formality(
        self, platform: str, platform_user: str, since: datetime
    ) -> float:
        """Ratio of technical vocabulary words to total words in user messages."""
        sql = sa.text(
            "SELECT m.content FROM messages m "
            "JOIN sessions s ON m.session_id = s.id "
            "WHERE s.platform = :platform AND s.platform_user = :platform_user "
            "AND m.role = 'user' AND m.created_at >= :since"
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
            rows = result.fetchall()

        total_words = 0
        tech_words = 0
        for row in rows:
            words = _WORD_RE.findall((row.content or "").lower())
            total_words += len(words)
            tech_words += sum(1 for w in words if w in TECHNICAL_VOCABULARY)

        if total_words == 0:
            return 0.0
        return round(tech_words / total_words, 4)

    async def _compute_top_topics(
        self, platform: str, platform_user: str, since: datetime
    ) -> list[str]:
        """Top-5 memory tags by frequency for this user's sessions in window."""
        sql = sa.text(
            "SELECT m.tags FROM memory m "
            "JOIN sessions s ON m.session_id = s.id "
            "WHERE s.platform = :platform AND s.platform_user = :platform_user "
            "AND m.created_at >= :since"
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
            rows = result.fetchall()

        tag_counts: dict[str, int] = {}
        for row in rows:
            raw_tags = row.tags or ""
            if not raw_tags:
                continue
            tag_list = raw_tags.split("|") if "|" in raw_tags else raw_tags.split()
            for tag in tag_list:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        if not tag_counts:
            return []

        sorted_tags = sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))
        return [tag for tag, _ in sorted_tags[:5]]

    async def _compute_activity_window(
        self, platform: str, platform_user: str, since: datetime
    ) -> list[int]:
        """24-slot histogram of turn start hours."""
        sql = sa.text(
            "SELECT t.started_at FROM turns t "
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
            rows = result.fetchall()

        histogram = [0] * 24
        for row in rows:
            started_at = row.started_at
            if isinstance(started_at, str):
                started_at = datetime.fromisoformat(started_at)
            hour = started_at.hour
            histogram[hour] += 1

        return histogram
