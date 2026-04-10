"""Unit tests for MemoryStore."""

import pytest

from hestia.memory.store import Memory, MemoryStore
from hestia.persistence.db import Database


class TestMemoryStore:
    @pytest.fixture
    async def memory_store(self, tmp_path):
        """Create a MemoryStore with a fresh in-memory database."""
        db = Database("sqlite+aiosqlite:///:memory:")
        await db.connect()
        await db.create_tables()
        store = MemoryStore(db)
        await store.create_table()
        yield store
        await db.close()

    @pytest.mark.asyncio
    async def test_save_and_search(self, memory_store):
        """Can save a memory and find it via search."""
        await memory_store.save(
            "The capital of France is Paris", tags=["geography"]
        )
        results = await memory_store.search("Paris")
        assert len(results) == 1
        assert "Paris" in results[0].content

    @pytest.mark.asyncio
    async def test_search_returns_relevant_results(self, memory_store):
        """Search ranks relevant results higher."""
        await memory_store.save("Python is a programming language")
        await memory_store.save("The python snake is found in Asia")
        await memory_store.save("JavaScript is also a programming language")
        results = await memory_store.search("programming language")
        assert len(results) >= 2
        # Both programming-related results should be returned
        contents = [r.content for r in results]
        assert any("Python" in c for c in contents)
        assert any("JavaScript" in c for c in contents)

    @pytest.mark.asyncio
    async def test_search_no_results(self, memory_store):
        """Search returns empty list when nothing matches."""
        await memory_store.save("The sky is blue")
        results = await memory_store.search("quantum computing")
        assert results == []

    @pytest.mark.asyncio
    async def test_list_memories(self, memory_store):
        """Can list all memories."""
        await memory_store.save("Memory one")
        await memory_store.save("Memory two")
        memories = await memory_store.list_memories()
        assert len(memories) == 2

    @pytest.mark.asyncio
    async def test_list_memories_by_tag(self, memory_store):
        """Can filter memories by tag."""
        await memory_store.save("Important thing", tags=["important"])
        await memory_store.save("Trivial thing", tags=["trivial"])
        memories = await memory_store.list_memories(tag="important")
        assert len(memories) == 1
        assert "Important" in memories[0].content

    @pytest.mark.asyncio
    async def test_delete_memory(self, memory_store):
        """Can delete a memory."""
        mem = await memory_store.save("Delete me")
        assert await memory_store.count() == 1
        result = await memory_store.delete(mem.id)
        assert result is True
        assert await memory_store.count() == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, memory_store):
        """Deleting nonexistent memory returns False."""
        result = await memory_store.delete("mem_nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_count(self, memory_store):
        """Count returns the number of memories."""
        assert await memory_store.count() == 0
        await memory_store.save("One")
        assert await memory_store.count() == 1
        await memory_store.save("Two")
        assert await memory_store.count() == 2

    @pytest.mark.asyncio
    async def test_save_with_session_id(self, memory_store):
        """Memory records which session created it."""
        mem = await memory_store.save(
            "Session note", session_id="session_123"
        )
        assert mem.session_id == "session_123"

    @pytest.mark.asyncio
    async def test_search_limit(self, memory_store):
        """Search respects the limit parameter."""
        for i in range(10):
            await memory_store.save(f"Python tip number {i}")
        results = await memory_store.search("Python", limit=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_memory_dataclass(self):
        """Memory dataclass stores expected fields."""
        from datetime import datetime

        mem = Memory(
            id="mem_test",
            content="Test content",
            tags="tag1 tag2",
            created_at=datetime.now(),
            session_id="sess_123",
        )
        assert mem.id == "mem_test"
        assert mem.content == "Test content"
        assert mem.tags == "tag1 tag2"
        assert mem.session_id == "sess_123"

    @pytest.mark.asyncio
    async def test_search_fts5_syntax_and(self, memory_store):
        """FTS5 AND syntax works for search."""
        await memory_store.save("Python programming language")
        await memory_store.save("Python snake")
        await memory_store.save("Java programming")
        # AND requires both terms
        results = await memory_store.search("Python AND programming")
        assert len(results) == 1
        assert "Python" in results[0].content
        assert "programming" in results[0].content

    @pytest.mark.asyncio
    async def test_search_fts5_syntax_not(self, memory_store):
        """FTS5 NOT syntax works for search."""
        await memory_store.save("Python programming")
        await memory_store.save("Python snake")
        results = await memory_store.search("Python NOT snake")
        assert len(results) == 1
        assert "programming" in results[0].content

    @pytest.mark.asyncio
    async def test_search_fts5_phrase(self, memory_store):
        """FTS5 phrase search works."""
        await memory_store.save("machine learning is great")
        await memory_store.save("learning machine design")
        results = await memory_store.search('"machine learning"')
        assert len(results) == 1
        assert "machine learning" in results[0].content

    @pytest.mark.asyncio
    async def test_list_memories_distinct_tags(self, memory_store):
        """Tag filter matches exact tags, not stemming variants."""
        await memory_store.save("Project alpha", tags=["project"])
        await memory_store.save("Projects list", tags=["projects"])
        await memory_store.save("Personal journal", tags=["personal"])

        # Searching for "project" should only match "project", not "projects"
        results = await memory_store.list_memories(tag="project")
        assert len(results) == 1
        assert "Project alpha" in results[0].content

        # Searching for "projects" should only match "projects"
        results = await memory_store.list_memories(tag="projects")
        assert len(results) == 1
        assert "Projects list" in results[0].content

    @pytest.mark.asyncio
    async def test_list_memories_partial_tag_no_match(self, memory_store):
        """Tag filter does not match partial tokens."""
        await memory_store.save("Documentation", tags=["docs"])
        await memory_store.save("Doctor appointment", tags=["doctor"])

        # Searching for "doc" should not match "docs" or "doctor"
        results = await memory_store.list_memories(tag="doc")
        assert len(results) == 0

        # Searching for "docs" should match only "docs"
        results = await memory_store.list_memories(tag="docs")
        assert len(results) == 1
        assert "Documentation" in results[0].content
