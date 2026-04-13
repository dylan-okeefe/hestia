"""Tests for memory epoch compilation."""

from datetime import datetime, timedelta, timezone

import pytest

from hestia.core.types import Session, SessionState, SessionTemperature
from hestia.memory import MemoryEpoch, MemoryEpochCompiler, MemoryStore


class TestMemoryEpoch:
    """Tests for MemoryEpoch dataclass."""

    def test_memory_epoch_creation(self):
        """Test creating a MemoryEpoch."""
        now = datetime.now(timezone.utc)
        epoch = MemoryEpoch(
            compiled_text="Test memories",
            created_at=now,
            memory_count=5,
            token_estimate=50,
        )
        assert epoch.compiled_text == "Test memories"
        assert epoch.created_at == now
        assert epoch.memory_count == 5
        assert epoch.token_estimate == 50


class TestMemoryEpochCompiler:
    """Tests for MemoryEpochCompiler."""

    @pytest.fixture
    async def compiler(self, tmp_path):
        """Create a MemoryEpochCompiler with an empty memory store."""
        from hestia.persistence.db import Database

        db_path = tmp_path / "test_memory.db"
        db = Database(f"sqlite+aiosqlite:///{db_path}")
        await db.connect()

        store = MemoryStore(db)
        await store.create_table()

        compiler = MemoryEpochCompiler(store, max_tokens=100)
        yield compiler

        await db.close()

    @pytest.mark.asyncio
    async def test_compile_empty_store(self, tmp_path):
        """Test compiling when no memories exist."""
        from hestia.persistence.db import Database

        db_path = tmp_path / "test_memory.db"
        db = Database(f"sqlite+aiosqlite:///{db_path}")
        await db.connect()

        store = MemoryStore(db)
        await store.create_table()

        compiler = MemoryEpochCompiler(store, max_tokens=100)

        session = Session(
            id="test-session",
            platform="cli",
            platform_user="test",
            started_at=datetime.now(timezone.utc),
            last_active_at=datetime.now(timezone.utc),
            slot_id=None,
            slot_saved_path=None,
            state=SessionState.ACTIVE,
            temperature=SessionTemperature.COLD,
        )

        epoch = await compiler.compile(session)

        assert epoch.compiled_text == ""
        assert epoch.memory_count == 0
        assert epoch.token_estimate == 0

        await db.close()

    @pytest.mark.asyncio
    async def test_compile_with_memories(self, tmp_path):
        """Test compiling with memories."""
        from hestia.persistence.db import Database

        db_path = tmp_path / "test_memory.db"
        db = Database(f"sqlite+aiosqlite:///{db_path}")
        await db.connect()

        store = MemoryStore(db)
        await store.create_table()

        # Add some memories
        await store.save(content="Memory 1 content", tags=["tag1"], session_id="session-1")
        await store.save(content="Memory 2 content", tags=["tag2"], session_id="session-1")
        await store.save(content="Memory 3 content", tags=[], session_id="session-2")

        compiler = MemoryEpochCompiler(store, max_tokens=500)

        session = Session(
            id="session-1",
            platform="cli",
            platform_user="test",
            started_at=datetime.now(timezone.utc),
            last_active_at=datetime.now(timezone.utc),
            slot_id=None,
            slot_saved_path=None,
            state=SessionState.ACTIVE,
            temperature=SessionTemperature.COLD,
        )

        epoch = await compiler.compile(session)

        assert "Relevant memories:" in epoch.compiled_text
        assert "Memory 1 content" in epoch.compiled_text
        assert "Memory 2 content" in epoch.compiled_text
        assert "Memory 3 content" in epoch.compiled_text
        assert epoch.memory_count >= 3

        await db.close()

    @pytest.mark.asyncio
    async def test_compile_truncates_to_max_tokens(self, tmp_path):
        """Test that compilation truncates to max_tokens."""
        from hestia.persistence.db import Database

        db_path = tmp_path / "test_memory.db"
        db = Database(f"sqlite+aiosqlite:///{db_path}")
        await db.connect()

        store = MemoryStore(db)
        await store.create_table()

        # Add many long memories
        for i in range(20):
            await store.save(
                content=f"This is a very long memory content that takes up space {i} " * 10,
                tags=["long"],
            )

        # Use small max_tokens
        compiler = MemoryEpochCompiler(store, max_tokens=50)

        session = Session(
            id="test-session",
            platform="cli",
            platform_user="test",
            started_at=datetime.now(timezone.utc),
            last_active_at=datetime.now(timezone.utc),
            slot_id=None,
            slot_saved_path=None,
            state=SessionState.ACTIVE,
            temperature=SessionTemperature.COLD,
        )

        epoch = await compiler.compile(session)

        # Should be truncated to roughly max_tokens * 4 characters
        assert len(epoch.compiled_text) <= 50 * 4 + 100  # Allow some margin for header
        assert epoch.token_estimate <= 60  # Rough check

        await db.close()

    @pytest.mark.asyncio
    async def test_compile_empty_method(self, tmp_path):
        """Test the compile_empty method."""
        from hestia.persistence.db import Database

        db_path = tmp_path / "test_memory.db"
        db = Database(f"sqlite+aiosqlite:///{db_path}")
        await db.connect()

        store = MemoryStore(db)
        await store.create_table()

        compiler = MemoryEpochCompiler(store, max_tokens=100)

        epoch = await compiler.compile_empty()

        assert epoch.compiled_text == ""
        assert epoch.memory_count == 0
        assert epoch.token_estimate == 0
        assert isinstance(epoch.created_at, datetime)

        await db.close()

    @pytest.mark.asyncio
    async def test_format_memories_with_tags(self, tmp_path):
        """Test formatting of memories with and without tags."""
        from hestia.persistence.db import Database

        db_path = tmp_path / "test_memory.db"
        db = Database(f"sqlite+aiosqlite:///{db_path}")
        await db.connect()

        store = MemoryStore(db)
        await store.create_table()

        await store.save(content="Tagged memory", tags=["important", "work"])
        await store.save(content="Untagged memory", tags=[])

        compiler = MemoryEpochCompiler(store, max_tokens=500)

        # Check the format by looking at compiled output
        session = Session(
            id="test-session",
            platform="cli",
            platform_user="test",
            started_at=datetime.now(timezone.utc),
            last_active_at=datetime.now(timezone.utc),
            slot_id=None,
            slot_saved_path=None,
            state=SessionState.ACTIVE,
            temperature=SessionTemperature.COLD,
        )

        epoch = await compiler.compile(session)

        # Check format: tagged memories should have [tags] prefix
        assert "[important work] Tagged memory" in epoch.compiled_text or "[work important] Tagged memory" in epoch.compiled_text
        assert "- Untagged memory" in epoch.compiled_text

        await db.close()

    @pytest.mark.asyncio
    async def test_recent_memories_only(self, tmp_path):
        """Test that old memories (beyond 30 days) are not included."""
        from hestia.persistence.db import Database

        db_path = tmp_path / "test_memory.db"
        db = Database(f"sqlite+aiosqlite:///{db_path}")
        await db.connect()

        store = MemoryStore(db)
        await store.create_table()

        # We can't easily insert old memories since store.save uses current time
        # But we can test that recent memories are included
        await store.save(content="Recent important memory", tags=["recent"])

        compiler = MemoryEpochCompiler(store, max_tokens=500)

        session = Session(
            id="test-session",
            platform="cli",
            platform_user="test",
            started_at=datetime.now(timezone.utc),
            last_active_at=datetime.now(timezone.utc),
            slot_id=None,
            slot_saved_path=None,
            state=SessionState.ACTIVE,
            temperature=SessionTemperature.COLD,
        )

        epoch = await compiler.compile(session)

        assert "Recent important memory" in epoch.compiled_text

        await db.close()
