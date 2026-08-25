"""Scope-aware memory maintenance tests (Loop B).

Covers deterministic dedupe, LLM contradiction supersession, protected-set
isolation, and undo across the two-tier global/topic memory scopes.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from hestia.core.inference import InferenceClient
from hestia.core.types import ChatResponse, Message
from hestia.memory.maintenance.contradictions import ContradictionResolver
from hestia.memory.maintenance.dedupe import DeterministicDeduper
from hestia.memory.maintenance.undo import MaintenanceUndo
from hestia.memory.store import MemoryStore
from hestia.memory.topics import TopicStore
from hestia.persistence.db import Database
from hestia.persistence.maintenance_trace_store import MaintenanceTraceStore


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
async def trace_store(db):
    """MaintenanceTraceStore backed by the same database."""
    store = MaintenanceTraceStore(db)
    await store.create_table()
    yield store


class TestScopeAwareDeterministicDedupe:
    @pytest.mark.asyncio
    async def test_global_and_topic_identical_content_are_not_merged(
        self, memory_store, topic_store
    ):
        """A global memory and a topic memory with the same content stay separate."""
        topic = await topic_store.get_or_create_topic("cli", "alice", "notes")

        await memory_store.save_global(
            content="Favorite color is blue",
            platform="cli",
            platform_user="alice",
        )
        await memory_store.save(
            content="Favorite color is blue",
            platform="cli",
            platform_user="alice",
            topic_ids=[topic.id],
        )

        deduper = DeterministicDeduper(memory_store)
        result = await deduper.run("cli", "alice")

        assert result.merged_count == 0
        active = await memory_store.list_active_memories(platform="cli", platform_user="alice")
        assert len(active) == 2

    @pytest.mark.asyncio
    async def test_within_topic_duplicate_is_merged(
        self, memory_store, topic_store
    ):
        """Two topic-scoped memories in the same topic with identical content merge."""
        topic = await topic_store.get_or_create_topic("cli", "alice", "project")

        await memory_store.save(
            content="Standup is at 9am",
            platform="cli",
            platform_user="alice",
            topic_ids=[topic.id],
        )
        await asyncio.sleep(0.01)
        await memory_store.save(
            content="standup is at 9am",
            platform="cli",
            platform_user="alice",
            topic_ids=[topic.id],
        )

        deduper = DeterministicDeduper(memory_store)
        result = await deduper.run("cli", "alice")

        assert result.merged_count == 1
        active = await memory_store.list_active_memories(platform="cli", platform_user="alice")
        assert len(active) == 1

    @pytest.mark.asyncio
    async def test_within_global_duplicate_is_merged(
        self, memory_store
    ):
        """Two global memories with identical content merge."""
        await memory_store.save_global(
            content="I prefer dark mode",
            platform="cli",
            platform_user="alice",
        )
        await asyncio.sleep(0.01)
        await memory_store.save_global(
            content="I prefer dark mode",
            platform="cli",
            platform_user="alice",
        )

        deduper = DeterministicDeduper(memory_store)
        result = await deduper.run("cli", "alice")

        assert result.merged_count == 1
        active = await memory_store.list_active_memories(platform="cli", platform_user="alice")
        assert len(active) == 1

    @pytest.mark.asyncio
    async def test_protected_global_does_not_block_topic_dedupe(
        self, memory_store, topic_store
    ):
        """A protected global duplicate does not prevent topic-scope deduplication."""
        topic = await topic_store.get_or_create_topic("cli", "alice", "work")

        protected_global = await memory_store.save_global(
            content="Shared duplicate content",
            platform="cli",
            platform_user="alice",
        )
        await memory_store.pin(protected_global.id, pinned=True, allow_unscoped=True)

        await memory_store.save(
            content="Shared duplicate content",
            platform="cli",
            platform_user="alice",
            topic_ids=[topic.id],
        )
        await asyncio.sleep(0.01)
        await memory_store.save(
            content="Shared duplicate content",
            platform="cli",
            platform_user="alice",
            topic_ids=[topic.id],
        )

        deduper = DeterministicDeduper(memory_store)
        result = await deduper.run("cli", "alice")

        assert result.merged_count == 1
        assert result.skipped_protected_count == 1
        active = await memory_store.list_active_memories(platform="cli", platform_user="alice")
        assert len(active) == 2


class FakeInferenceClient(InferenceClient):
    """Inference client that returns deterministic contradiction JSON responses."""

    def __init__(
        self,
        responses: list[tuple[bool, float, str | None, str | None]] | None = None,
    ) -> None:
        super().__init__("http://localhost:8001", "dummy")
        self._responses = responses or []
        self.calls: list[list[Message]] = []

    async def chat(  # type: ignore[override]
        self,
        messages: list[Message],
        **_kwargs: object,
    ) -> ChatResponse:
        self.calls.append(messages)
        contradiction, confidence, attribute, reasoning = self._responses.pop(0)
        payload = {
            "contradiction": contradiction,
            "confidence": confidence,
            "attribute": attribute,
            "reasoning": reasoning,
        }
        return ChatResponse(
            content=json.dumps(payload),
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
        )


class TestScopeAwareSupersession:
    @pytest.mark.asyncio
    async def test_supersession_does_not_cross_scopes(
        self, memory_store, topic_store
    ):
        """A topic-scoped fact does not supersede a global fact and vice versa."""
        topic = await topic_store.get_or_create_topic("cli", "alice", "location")

        await memory_store.save_global(
            content="User lives in NYC.",
            platform="cli",
            platform_user="alice",
        )
        await asyncio.sleep(0.01)
        await memory_store.save(
            content="User lives in LA.",
            platform="cli",
            platform_user="alice",
            topic_ids=[topic.id],
        )

        inference = FakeInferenceClient(
            [(True, 0.95, "city", "User changed cities; newer fact wins.")]
        )
        resolver = ContradictionResolver(memory_store, inference)
        result = await resolver.run("cli", "alice")

        assert result.superseded_count == 0
        assert result.examined_count == 0
        active = await memory_store.list_active_memories(platform="cli", platform_user="alice")
        assert len(active) == 2

    @pytest.mark.asyncio
    async def test_within_topic_supersession_replaces_older_fact(
        self, memory_store, topic_store
    ):
        """A contradictory topic-scoped fact supersedes the older one."""
        topic = await topic_store.get_or_create_topic("cli", "alice", "location")

        older = await memory_store.save(
            content="User lives in NYC.",
            platform="cli",
            platform_user="alice",
            topic_ids=[topic.id],
        )
        await asyncio.sleep(0.01)
        newer = await memory_store.save(
            content="User lives in LA.",
            platform="cli",
            platform_user="alice",
            topic_ids=[topic.id],
        )

        inference = FakeInferenceClient(
            [(True, 0.95, "city", "User changed cities; newer fact wins.")]
        )
        resolver = ContradictionResolver(memory_store, inference)
        result = await resolver.run("cli", "alice")

        assert result.superseded_count == 1
        assert result.examined_count == 1
        active = await memory_store.list_active_memories(platform="cli", platform_user="alice")
        assert len(active) == 1
        assert active[0].id == newer.id

        inactive = await memory_store.list_inactive_memories(platform="cli", platform_user="alice")
        assert len(inactive) == 1
        assert inactive[0].id == older.id
        assert inactive[0].superseded_by == newer.id


class TestScopeAwareUndo:
    @pytest.mark.asyncio
    async def test_undo_of_scoped_action_does_not_affect_other_scopes(
        self, memory_store, topic_store, trace_store
    ):
        """Undoing a topic-scope merge leaves a global-scope merge untouched."""
        topic = await topic_store.get_or_create_topic("cli", "alice", "todo")

        await memory_store.save_global(
            content="Global duplicate",
            platform="cli",
            platform_user="alice",
        )
        await asyncio.sleep(0.01)
        await memory_store.save_global(
            content="Global duplicate",
            platform="cli",
            platform_user="alice",
        )

        await memory_store.save(
            content="Topic duplicate",
            platform="cli",
            platform_user="alice",
            topic_ids=[topic.id],
        )
        await asyncio.sleep(0.01)
        await memory_store.save(
            content="Topic duplicate",
            platform="cli",
            platform_user="alice",
            topic_ids=[topic.id],
        )

        deduper = DeterministicDeduper(memory_store, trace_store=trace_store)
        await deduper.run("cli", "alice")

        actions = await trace_store.list_recent(platform="cli", platform_user="alice")
        merge_actions = [a for a in actions if a.action == "merge"]
        assert len(merge_actions) == 2

        # Identify the topic-scope merge by its recorded scope details.
        topic_action = next(
            a
            for a in merge_actions
            if isinstance(a.details.get("scope"), str)
            and a.details["scope"] != "global"
        )
        global_action = next(
            a
            for a in merge_actions
            if a.details.get("scope") == "global"
        )

        undo = MaintenanceUndo(
            memory_store,
            trace_store,
            undo_retention_days=7,
        )
        result = await undo.undo(topic_action.id)
        assert result.restored_count == 1

        # The topic loser is restored; the global loser stays inactive.
        topic_loser = await memory_store.get(topic_action.loser_memory_ids[0])
        global_loser = await memory_store.get(global_action.loser_memory_ids[0])
        assert topic_loser is not None
        assert topic_loser.is_active is True
        assert global_loser is not None
        assert global_loser.is_active is False
