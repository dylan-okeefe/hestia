"""Unit tests for topic-scoped memory (Loop A)."""

from __future__ import annotations

import pytest

from hestia.commands.meta import get_default_registry
from hestia.core.types import Session, SessionState, SessionTemperature
from hestia.memory.epochs import MemoryEpochCompiler
from hestia.memory.store import MemoryStore
from hestia.memory.topics import TopicStore
from hestia.persistence.db import Database
from hestia.persistence.session_store import SessionStore


@pytest.fixture
async def db():
    """In-memory database with all schema tables created."""
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.connect()
    await database.create_tables()
    yield database
    await database.close()


@pytest.fixture
async def memory_store(db):
    """MemoryStore with a freshly-created memory table."""
    store = MemoryStore(db)
    await store.create_table()
    yield store


@pytest.fixture
async def topic_store(db):
    """TopicStore backed by the same database."""
    yield TopicStore(db)


@pytest.fixture
def sample_session() -> Session:
    """A sample session to use as a conversation."""
    from datetime import datetime

    return Session(
        id="conv-1",
        platform="cli",
        platform_user="alice",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )


class TestTopicSaveAndRetrieval:
    @pytest.mark.asyncio
    async def test_save_associates_memory_with_all_subscribed_topics(
        self, memory_store, topic_store, sample_session
    ):
        """A topic-scoped save lands in every currently subscribed topic."""
        topic_a = await topic_store.get_or_create_topic(
            sample_session.platform, sample_session.platform_user, "project-x"
        )
        topic_b = await topic_store.get_or_create_topic(
            sample_session.platform, sample_session.platform_user, "recipes"
        )
        await topic_store.subscribe_conversation(sample_session.id, topic_a.id)
        await topic_store.subscribe_conversation(sample_session.id, topic_b.id)

        mem = await memory_store.save(
            content="Standup is at 9am",
            session_id=sample_session.id,
            platform=sample_session.platform,
            platform_user=sample_session.platform_user,
            topic_ids=[topic_a.id, topic_b.id],
        )
        assert mem is not None
        assert mem.is_global is False

        global_memories, topic_memories = await memory_store.get_for_epoch(
            platform=sample_session.platform,
            platform_user=sample_session.platform_user,
            topic_ids=[topic_a.id, topic_b.id],
        )
        assert global_memories == []
        assert len(topic_memories) == 1
        assert topic_memories[0].id == mem.id

    @pytest.mark.asyncio
    async def test_global_and_topic_memory_with_same_content_are_not_merged(
        self, memory_store, topic_store, sample_session
    ):
        """Identical content in different scopes stays as separate rows."""
        topic = await topic_store.get_or_create_topic(
            sample_session.platform, sample_session.platform_user, "notes"
        )
        await topic_store.subscribe_conversation(sample_session.id, topic.id)

        global_mem = await memory_store.save_global(
            content="Favorite color is blue",
            session_id=sample_session.id,
            platform=sample_session.platform,
            platform_user=sample_session.platform_user,
        )
        topic_mem = await memory_store.save(
            content="Favorite color is blue",
            session_id=sample_session.id,
            platform=sample_session.platform,
            platform_user=sample_session.platform_user,
            topic_ids=[topic.id],
        )

        assert global_mem is not None
        assert topic_mem is not None
        assert global_mem.id != topic_mem.id

        globals_, topics_ = await memory_store.get_for_epoch(
            platform=sample_session.platform,
            platform_user=sample_session.platform_user,
            topic_ids=[topic.id],
        )
        assert len(globals_) == 1
        assert len(topics_) == 1


class TestImplicitTopicMigration:
    @pytest.mark.asyncio
    async def test_add_topic_migrates_implicit_memories_once(
        self, memory_store, topic_store, sample_session
    ):
        """First /add-topic moves implicit memories into the new topic."""
        implicit_topic = await topic_store.get_or_create_implicit_topic(
            sample_session.platform, sample_session.platform_user, sample_session.id
        )
        await topic_store.subscribe_conversation(sample_session.id, implicit_topic.id)

        mem = await memory_store.save(
            content="Implicit room memory",
            session_id=sample_session.id,
            platform=sample_session.platform,
            platform_user=sample_session.platform_user,
            topic_ids=[implicit_topic.id],
        )
        assert mem is not None

        # First explicit topic add should migrate the implicit memory.
        explicit = await topic_store.get_or_create_topic(
            sample_session.platform, sample_session.platform_user, "work"
        )
        migrated = await topic_store.migrate_implicit_memories(
            sample_session.id,
            explicit.id,
            platform=sample_session.platform,
            platform_user=sample_session.platform_user,
        )
        assert migrated == 1

        # After migration the memory should be retrievable under the explicit topic.
        globals_, topics_ = await memory_store.get_for_epoch(
            platform=sample_session.platform,
            platform_user=sample_session.platform_user,
            topic_ids=[explicit.id],
        )
        assert len(topics_) == 1
        assert topics_[0].id == mem.id

        # The conversation should no longer be subscribed to the implicit topic.
        subs = await topic_store.list_conversation_topics(sample_session.id)
        assert implicit_topic.id not in {t.id for t in subs}

    @pytest.mark.asyncio
    async def test_later_add_topic_does_not_retroactively_migrate(
        self, memory_store, topic_store, sample_session
    ):
        """Subsequent topic adds only affect future saves."""
        implicit_topic = await topic_store.get_or_create_implicit_topic(
            sample_session.platform, sample_session.platform_user, sample_session.id
        )
        await topic_store.subscribe_conversation(sample_session.id, implicit_topic.id)

        await memory_store.save(
            content="Only in implicit pool",
            session_id=sample_session.id,
            platform=sample_session.platform,
            platform_user=sample_session.platform_user,
            topic_ids=[implicit_topic.id],
        )

        first = await topic_store.get_or_create_topic(
            sample_session.platform, sample_session.platform_user, "first"
        )
        await topic_store.migrate_implicit_memories(
            sample_session.id,
            first.id,
            platform=sample_session.platform,
            platform_user=sample_session.platform_user,
        )

        second = await topic_store.get_or_create_topic(
            sample_session.platform, sample_session.platform_user, "second"
        )
        later_migrated = await topic_store.migrate_implicit_memories(
            sample_session.id,
            second.id,
            platform=sample_session.platform,
            platform_user=sample_session.platform_user,
        )
        assert later_migrated == 0

        # The implicit memory is in 'first' but not 'second'.
        _, first_topics = await memory_store.get_for_epoch(
            platform=sample_session.platform,
            platform_user=sample_session.platform_user,
            topic_ids=[first.id],
        )
        _, second_topics = await memory_store.get_for_epoch(
            platform=sample_session.platform,
            platform_user=sample_session.platform_user,
            topic_ids=[second.id],
        )
        assert len(first_topics) == 1
        assert len(second_topics) == 0


class TestRemoveTopic:
    @pytest.mark.asyncio
    async def test_remove_topic_leaves_memory_associations_intact(
        self, memory_store, topic_store, sample_session
    ):
        """Unsubscribing does not delete memory_topics rows."""
        topic = await topic_store.get_or_create_topic(
            sample_session.platform, sample_session.platform_user, "hobby"
        )
        await topic_store.subscribe_conversation(sample_session.id, topic.id)

        mem = await memory_store.save(
            content="Painting technique",
            session_id=sample_session.id,
            platform=sample_session.platform,
            platform_user=sample_session.platform_user,
            topic_ids=[topic.id],
        )

        # Remove subscription.
        removed = await topic_store.unsubscribe_conversation(sample_session.id, topic.id)
        assert removed is True

        # Memory association still exists.
        _, topics_ = await memory_store.get_for_epoch(
            platform=sample_session.platform,
            platform_user=sample_session.platform_user,
            topic_ids=[topic.id],
        )
        assert len(topics_) == 1
        assert topics_[0].id == mem.id


class TestEpochComposition:
    @pytest.mark.asyncio
    async def test_epoch_respects_global_cap_and_slack(
        self, memory_store, topic_store, sample_session
    ):
        """Global pool is capped; leftover budget flows to topics."""
        topic = await topic_store.get_or_create_topic(
            sample_session.platform, sample_session.platform_user, "project"
        )
        await topic_store.subscribe_conversation(sample_session.id, topic.id)

        # Global memories are larger than the 30% cap.
        for i in range(3):
            await memory_store.save_global(
                content=f"Global preference {i}: " + "x" * 50,
                platform=sample_session.platform,
                platform_user=sample_session.platform_user,
            )

        # Topic memories should fill the remaining budget.
        for i in range(10):
            await memory_store.save(
                content=f"Topic fact {i}",
                platform=sample_session.platform,
                platform_user=sample_session.platform_user,
                topic_ids=[topic.id],
            )

        compiler = MemoryEpochCompiler(
            memory_store, max_tokens=100, global_cap_ratio=0.3
        )
        epoch = await compiler.compile(
            sample_session, topic_ids=[topic.id]
        )

        assert epoch.memory_count > 0
        # Global cap at 30 tokens means at most one ~17-token global memory.
        assert epoch.token_estimate <= 100
        assert "Global preference" in epoch.compiled_text
        assert "Topic fact" in epoch.compiled_text

    @pytest.mark.asyncio
    async def test_group_chat_epoch_uses_per_sender_global(
        self, memory_store, topic_store, sample_session
    ):
        """Group chat epoch includes active sender's global + room topics."""
        topic = await topic_store.get_or_create_topic(
            sample_session.platform, sample_session.platform_user, "room-topic"
        )
        await topic_store.subscribe_conversation(sample_session.id, topic.id)

        # Alice's global memory.
        await memory_store.save_global(
            content="Alice likes dark mode",
            platform=sample_session.platform,
            platform_user="alice",
        )
        # Bob's global memory.
        await memory_store.save_global(
            content="Bob likes light mode",
            platform=sample_session.platform,
            platform_user="bob",
        )
        # Room topic memory.
        await memory_store.save(
            content="Room decision: use tabs",
            platform=sample_session.platform,
            platform_user=sample_session.platform_user,
            topic_ids=[topic.id],
        )

        compiler = MemoryEpochCompiler(memory_store, max_tokens=500)

        # Active sender is Bob; his global should appear, Alice's should not.
        epoch = await compiler.compile(
            sample_session,
            topic_ids=[topic.id],
            active_sender_platform_user="bob",
        )

        assert "Bob likes light mode" in epoch.compiled_text
        assert "Alice likes dark mode" not in epoch.compiled_text
        assert "Room decision: use tabs" in epoch.compiled_text


class TestExistingMemoryMigration:
    @pytest.mark.asyncio
    async def test_existing_memories_read_as_global_after_migration(
        self, db, sample_session
    ):
        """Memories created before the topic feature become global on upgrade."""
        import sqlalchemy as sa

        from hestia.core.clock import utcnow

        # Simulate an old-style memory table by creating it without is_global
        # and inserting a legacy row, then letting MemoryStore migrate it.
        store = MemoryStore(db)
        await store.create_table()

        # Insert a legacy row as if it predates the is_global column.
        async with db.engine.connect() as conn:
            await conn.execute(
                sa.text(
                    "INSERT INTO memory (id, content, tags, session_id, created_at, "
                    "platform, platform_user, is_active, is_pinned, is_user_authored, "
                    "is_global) "
                    "VALUES (:id, :content, :tags, :session_id, :created_at, "
                    ":platform, :platform_user, 1, 0, 0, NULL)"
                ),
                {
                    "id": "mem_legacy_1",
                    "content": "Legacy fact",
                    "tags": "",
                    "session_id": sample_session.id,
                    "created_at": utcnow().isoformat(),
                    "platform": sample_session.platform,
                    "platform_user": sample_session.platform_user,
                },
            )
            await conn.commit()

        # Re-run create_table to trigger the migration.
        await store.create_table()

        fetched = await store.get("mem_legacy_1")
        assert fetched is not None
        assert fetched.is_global is True


class TestTopicCommands:
    @pytest.mark.asyncio
    async def test_add_topic_command(self, db, sample_session, capsys):
        """/add-topic subscribes the conversation and migrates implicit memories."""
        store = SessionStore(db)
        memory_store = MemoryStore(db)
        await memory_store.create_table()
        topic_store = TopicStore(db)

        # Save an implicit memory first.
        implicit = await topic_store.get_or_create_implicit_topic(
            sample_session.platform, sample_session.platform_user, sample_session.id
        )
        await topic_store.subscribe_conversation(sample_session.id, implicit.id)
        await memory_store.save(
            content="Implicit note",
            session_id=sample_session.id,
            platform=sample_session.platform,
            platform_user=sample_session.platform_user,
            topic_ids=[implicit.id],
        )

        app_mock = type(
            "App",
            (object,),
            {"memory_store": memory_store, "topic_store": topic_store},
        )()

        reg = get_default_registry()
        should_exit, _ = await reg.handle(
            "/add-topic work",
            sample_session,
            store,
            app=app_mock,
        )
        assert should_exit is False
        captured = capsys.readouterr()
        assert "Subscribed to topic 'work'" in captured.out
        assert "migrated 1 implicit memory" in captured.out

    @pytest.mark.asyncio
    async def test_remember_global_command(self, db, sample_session, capsys):
        """/remember-global saves a global memory."""
        store = SessionStore(db)
        memory_store = MemoryStore(db)
        await memory_store.create_table()
        topic_store = TopicStore(db)

        app_mock = type(
            "App",
            (object,),
            {"memory_store": memory_store, "topic_store": topic_store},
        )()

        reg = get_default_registry()
        should_exit, _ = await reg.handle(
            "/remember-global I prefer metric units",
            sample_session,
            store,
            app=app_mock,
        )
        assert should_exit is False
        captured = capsys.readouterr()
        assert "Saved global memory" in captured.out

        globals_, topics_ = await memory_store.get_for_epoch(
            platform=sample_session.platform,
            platform_user=sample_session.platform_user,
        )
        assert len(globals_) == 1
        assert "metric units" in globals_[0].content
        assert topics_ == []

    @pytest.mark.asyncio
    async def test_topic_command_lists_subscriptions(
        self, db, sample_session, capsys
    ):
        """/topic prints the conversation's subscriptions."""
        store = SessionStore(db)
        memory_store = MemoryStore(db)
        await memory_store.create_table()
        topic_store = TopicStore(db)

        topic = await topic_store.get_or_create_topic(
            sample_session.platform, sample_session.platform_user, "work"
        )
        await topic_store.subscribe_conversation(sample_session.id, topic.id)

        app_mock = type(
            "App",
            (object,),
            {"memory_store": memory_store, "topic_store": topic_store},
        )()

        reg = get_default_registry()
        should_exit, _ = await reg.handle(
            "/topic",
            sample_session,
            store,
            app=app_mock,
        )
        assert should_exit is False
        captured = capsys.readouterr()
        assert "Subscribed topics:" in captured.out
        assert "- work" in captured.out

    @pytest.mark.asyncio
    async def test_remove_topic_command(self, db, sample_session, capsys):
        """/remove-topic unsubscribes but leaves memory associations intact."""
        store = SessionStore(db)
        memory_store = MemoryStore(db)
        await memory_store.create_table()
        topic_store = TopicStore(db)

        topic = await topic_store.get_or_create_topic(
            sample_session.platform, sample_session.platform_user, "hobby"
        )
        await topic_store.subscribe_conversation(sample_session.id, topic.id)
        mem = await memory_store.save(
            content="Painting tip",
            session_id=sample_session.id,
            platform=sample_session.platform,
            platform_user=sample_session.platform_user,
            topic_ids=[topic.id],
        )

        app_mock = type(
            "App",
            (object,),
            {"memory_store": memory_store, "topic_store": topic_store},
        )()

        reg = get_default_registry()
        should_exit, _ = await reg.handle(
            "/remove-topic hobby",
            sample_session,
            store,
            app=app_mock,
        )
        assert should_exit is False
        captured = capsys.readouterr()
        assert "Unsubscribed from topic 'hobby'" in captured.out

        # Memory association remains.
        _, topics_ = await memory_store.get_for_epoch(
            platform=sample_session.platform,
            platform_user=sample_session.platform_user,
            topic_ids=[topic.id],
        )
        assert len(topics_) == 1
        assert topics_[0].id == mem.id
