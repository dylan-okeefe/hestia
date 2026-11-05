"""Per-chat settings persistence (L250).

Stores small per-conversation preferences — currently the thinking/reasoning
display toggle — keyed by ``(platform, platform_user, key)`` where
``platform_user`` is the chat id the platform adapter dispatches on.

Reads go through an in-memory cache so the hot path in
``orchestrator/execution.py`` pays no DB round-trip per turn; the SQLite
table remains the source of truth and the cache is updated on every write.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa

from hestia.core.clock import utcnow

if TYPE_CHECKING:
    from hestia.persistence.db import Database

SHOW_THINKING_KEY = "show_thinking"
AGENT_BACKEND_KEY = "agent_backend"
"""Per-chat coding-agent backend override for the Telegram bridge (L251)."""
KIMI_SESSION_ID_KEY = "kimi_session_id"
"""Persisted Kimi CLI session id for chat continuity (L251)."""


class ChatSettingsStore:
    """Per-chat settings with an in-memory read cache over the DB table."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._cache: dict[tuple[str, str, str], str | None] = {}

    async def get(self, platform: str, platform_user: str, key: str) -> str | None:
        """Return the stored value, or None when no explicit override exists."""
        cache_key = (platform, platform_user, key)
        if cache_key in self._cache:
            return self._cache[cache_key]
        sql = sa.text(
            "SELECT value FROM chat_settings "
            "WHERE platform = :platform AND platform_user = :platform_user AND key = :key"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(
                sql,
                {"platform": platform, "platform_user": platform_user, "key": key},
            )
            row = result.fetchone()
        value = row[0] if row else None
        self._cache[cache_key] = value
        return value

    async def set(self, platform: str, platform_user: str, key: str, value: str) -> None:
        """Insert or update a setting and refresh the cache."""
        sql = sa.text(
            "INSERT INTO chat_settings (platform, platform_user, key, value, updated_at) "
            "VALUES (:platform, :platform_user, :key, :value, :updated_at) "
            "ON CONFLICT (platform, platform_user, key) DO UPDATE SET "
            "value = EXCLUDED.value, "
            "updated_at = EXCLUDED.updated_at"
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(
                sql,
                {
                    "platform": platform,
                    "platform_user": platform_user,
                    "key": key,
                    "value": value,
                    "updated_at": utcnow(),
                },
            )
            await conn.commit()
        self._cache[(platform, platform_user, key)] = value

    async def get_show_thinking(self, platform: str, platform_user: str) -> bool | None:
        """Return the explicit thinking-display override for a chat, if any."""
        value = await self.get(platform, platform_user, SHOW_THINKING_KEY)
        if value is None:
            return None
        return value == "1"

    async def set_show_thinking(
        self, platform: str, platform_user: str, enabled: bool
    ) -> None:
        """Persist the thinking-display override for a chat."""
        await self.set(platform, platform_user, SHOW_THINKING_KEY, "1" if enabled else "0")

    async def get_agent_backend(self, platform: str, platform_user: str) -> str | None:
        """Return the stored agent-bridge backend override (``pi``/``kimi``), if any."""
        return await self.get(platform, platform_user, AGENT_BACKEND_KEY)

    async def set_agent_backend(self, platform: str, platform_user: str, backend: str) -> None:
        """Persist the agent-bridge backend override for a chat."""
        await self.set(platform, platform_user, AGENT_BACKEND_KEY, backend)

    async def get_kimi_session_id(self, platform: str, platform_user: str) -> str | None:
        """Return the persisted Kimi CLI session id for a chat, if any."""
        return await self.get(platform, platform_user, KIMI_SESSION_ID_KEY)

    async def set_kimi_session_id(self, platform: str, platform_user: str, session_id: str) -> None:
        """Persist the Kimi CLI session id so later turns resume the same session."""
        await self.set(platform, platform_user, KIMI_SESSION_ID_KEY, session_id)

    def clear_cache(self) -> None:
        """Drop all cached values so the next read re-queries the DB."""
        self._cache.clear()
