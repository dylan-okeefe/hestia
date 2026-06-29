"""Topic management for thread/topic-scoped memory.

Topics are user-named retrieval scopes separate from descriptive tags. A
conversation can subscribe to one or more topics; memories saved in that
conversation are associated with all subscribed topics. The implicit per-
conversation pool is modeled as an auto topic named ``room:<conversation_id>``.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa

from hestia.core.clock import utcnow
from hestia.persistence.db import Database

logger = logging.getLogger(__name__)


def implicit_topic_name(conversation_id: str) -> str:
    """Return the reserved implicit topic name for a conversation."""
    return f"room:{conversation_id}"


@dataclass
class Topic:
    """A user-named retrieval scope."""

    id: str
    platform: str
    platform_user: str
    name: str
    created_at: datetime


class TopicStore:
    """Persistence for topics and conversation subscriptions."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def get_or_create_topic(
        self,
        platform: str,
        platform_user: str,
        name: str,
    ) -> Topic:
        """Fetch an existing topic or create it."""
        existing = await self.get_topic(platform, platform_user, name)
        if existing is not None:
            return existing

        topic_id = f"topic_{uuid.uuid4().hex[:16]}"
        now = utcnow()
        sql = sa.text(
            "INSERT OR IGNORE INTO topics (id, platform, platform_user, name, created_at) "
            "VALUES (:id, :platform, :platform_user, :name, :created_at)"
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(
                sql,
                {
                    "id": topic_id,
                    "platform": platform,
                    "platform_user": platform_user,
                    "name": name,
                    "created_at": now.isoformat(),
                },
            )
            await conn.commit()

        existing = await self.get_topic(platform, platform_user, name)
        if existing is None:
            raise RuntimeError(
                f"Failed to create or fetch topic {name!r} for {platform}/{platform_user}"
            )
        return existing

    async def get_topic(
        self,
        platform: str,
        platform_user: str,
        name: str,
    ) -> Topic | None:
        """Fetch a topic by scoped name."""
        sql = sa.text(
            "SELECT id, platform, platform_user, name, created_at FROM topics "
            "WHERE platform = :platform AND platform_user = :platform_user AND name = :name"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(
                sql,
                {"platform": platform, "platform_user": platform_user, "name": name},
            )
            row = result.fetchone()
            if row is None:
                return None
            return self._row_to_topic(row)

    async def get_topic_by_id(self, topic_id: str) -> Topic | None:
        """Fetch a topic by ID."""
        sql = sa.text(
            "SELECT id, platform, platform_user, name, created_at FROM topics WHERE id = :id"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"id": topic_id})
            row = result.fetchone()
            if row is None:
                return None
            return self._row_to_topic(row)

    async def subscribe_conversation(
        self,
        conversation_id: str,
        topic_id: str,
    ) -> None:
        """Subscribe a conversation to a topic."""
        now = utcnow()
        sql = sa.text(
            "INSERT OR IGNORE INTO conversation_topics "
            "(conversation_id, topic_id, created_at) "
            "VALUES (:conversation_id, :topic_id, :created_at)"
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(
                sql,
                {
                    "conversation_id": conversation_id,
                    "topic_id": topic_id,
                    "created_at": now.isoformat(),
                },
            )
            await conn.commit()

    async def unsubscribe_conversation(
        self,
        conversation_id: str,
        topic_id: str,
    ) -> bool:
        """Unsubscribe a conversation from a topic.

        Returns True if a subscription row was removed.
        """
        sql = sa.text(
            "DELETE FROM conversation_topics "
            "WHERE conversation_id = :conversation_id AND topic_id = :topic_id"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(
                sql,
                {"conversation_id": conversation_id, "topic_id": topic_id},
            )
            await conn.commit()
            return result.rowcount > 0

    async def list_conversation_topics(
        self,
        conversation_id: str,
    ) -> list[Topic]:
        """Return all topics subscribed by a conversation."""
        sql = sa.text(
            "SELECT t.id, t.platform, t.platform_user, t.name, t.created_at "
            "FROM topics t "
            "JOIN conversation_topics ct ON t.id = ct.topic_id "
            "WHERE ct.conversation_id = :conversation_id "
            "ORDER BY t.name"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(
                sql, {"conversation_id": conversation_id}
            )
            return [self._row_to_topic(row) for row in result.fetchall()]

    async def get_conversation_topic_ids(
        self,
        conversation_id: str,
    ) -> list[str]:
        """Return topic IDs subscribed by a conversation."""
        topics = await self.list_conversation_topics(conversation_id)
        return [t.id for t in topics]

    async def migrate_implicit_memories(
        self,
        conversation_id: str,
        topic_id: str,
        platform: str | None = None,
        platform_user: str | None = None,
    ) -> int:
        """Move a conversation's implicit memories into a topic.

        On the first explicit topic add, memories that were saved to the
        implicit ``room:<conversation_id>`` topic are copied to the new topic
        and their implicit association is removed. Existing memory rows are
        not modified; only ``memory_topics`` associations change.

        Returns the number of memories migrated.
        """
        implicit_name = implicit_topic_name(conversation_id)
        implicit_topic = await self.get_topic(
            platform or "", platform_user or "", implicit_name
        )
        if implicit_topic is None:
            return 0

        # Copy implicit associations to the new topic.
        now = utcnow()
        copy_sql = sa.text(
            "INSERT OR IGNORE INTO memory_topics (memory_id, topic_id, created_at) "
            "SELECT memory_id, :topic_id, :created_at "
            "FROM memory_topics "
            "WHERE topic_id = :implicit_topic_id"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(
                copy_sql,
                {
                    "topic_id": topic_id,
                    "implicit_topic_id": implicit_topic.id,
                    "created_at": now.isoformat(),
                },
            )
            migrated = result.rowcount or 0

            # Drop the conversation's implicit subscription and the implicit
            # memory associations so later topic adds do not re-migrate.
            await conn.execute(
                sa.text(
                    "DELETE FROM conversation_topics "
                    "WHERE conversation_id = :conversation_id AND topic_id = :implicit_topic_id"
                ),
                {
                    "conversation_id": conversation_id,
                    "implicit_topic_id": implicit_topic.id,
                },
            )
            await conn.execute(
                sa.text(
                    "DELETE FROM memory_topics WHERE topic_id = :implicit_topic_id"
                ),
                {"implicit_topic_id": implicit_topic.id},
            )
            await conn.commit()

        logger.info(
            "Migrated %d implicit memories from %s to topic %s for conversation %s",
            migrated,
            implicit_name,
            topic_id,
            conversation_id,
        )
        return migrated

    async def get_or_create_implicit_topic(
        self,
        platform: str,
        platform_user: str,
        conversation_id: str,
    ) -> Topic:
        """Create or fetch the implicit per-conversation topic."""
        return await self.get_or_create_topic(
            platform, platform_user, implicit_topic_name(conversation_id)
        )

    async def resolve_capture_topic_ids(
        self,
        conversation_id: str,
        platform: str,
        platform_user: str,
    ) -> list[str]:
        """Return the topic IDs a new memory in this conversation should target.

        If the conversation already has explicit topic subscriptions, return those.
        Otherwise, get-or-create the implicit per-conversation topic, subscribe the
        conversation to it, and return the implicit topic ID. This ensures every
        non-global memory is reachable by the read path and by later migration when
        the user adds their first explicit topic.
        """
        topic_ids = await self.get_conversation_topic_ids(conversation_id)
        if topic_ids:
            return topic_ids

        implicit = await self.get_or_create_implicit_topic(
            platform, platform_user, conversation_id
        )
        await self.subscribe_conversation(conversation_id, implicit.id)
        return [implicit.id]

    def _row_to_topic(self, row: Any) -> Topic:
        created_at = row.created_at
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        return Topic(
            id=row.id,
            platform=row.platform,
            platform_user=row.platform_user,
            name=row.name,
            created_at=created_at,
        )
