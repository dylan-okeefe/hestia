"""Unit tests for the LLM contradiction detection / supersession pass (L230)."""

from __future__ import annotations

import json

import pytest

from hestia.core.inference import InferenceClient
from hestia.core.types import ChatResponse, Message
from hestia.memory.maintenance.contradictions import (
    ContradictionResolver,
    SupersessionResult,
)
from hestia.memory.store import MemoryStore
from hestia.persistence.db import Database


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


@pytest.fixture
async def memory_store():
    """Create a MemoryStore with a fresh in-memory database."""
    db = Database("sqlite+aiosqlite:///:memory:")
    await db.connect()
    await db.create_tables()
    store = MemoryStore(db)
    await store.create_table()
    yield store
    await db.close()


@pytest.fixture
def inference():
    """Create a FakeInferenceClient with no pre-programmed responses."""
    return FakeInferenceClient()


@pytest.fixture
def resolver(memory_store, inference):
    """Create a ContradictionResolver bound to the test store and fake inference."""
    return ContradictionResolver(memory_store, inference)


class TestConfidentContradictionSupersedesOlder:
    @pytest.mark.asyncio
    async def test_confident_contradiction_supersedes_older(
        self,
        memory_store: MemoryStore,
        resolver: ContradictionResolver,
        inference: FakeInferenceClient,
    ) -> None:
        """A high-confidence same-attribute contradiction supersedes the older memory."""
        older = await memory_store.save(
            content="User lives in NYC.",
            tags=["location"],
            platform="cli",
            platform_user="alice",
        )
        newer = await memory_store.save(
            content="User lives in LA.",
            tags=["location"],
            platform="cli",
            platform_user="alice",
        )

        inference._responses.append(
            (True, 0.95, "city", "User changed cities; newer fact wins.")
        )

        result = await resolver.run("cli", "alice")

        assert isinstance(result, SupersessionResult)
        assert result.superseded_count == 1
        assert result.examined_count == 1
        assert len(inference.calls) == 1

        active = await memory_store.list_active_memories(
            platform="cli", platform_user="alice"
        )
        assert len(active) == 1
        assert active[0].id == newer.id

        inactive = await memory_store.list_inactive_memories(
            platform="cli", platform_user="alice"
        )
        assert len(inactive) == 1
        assert inactive[0].id == older.id
        assert inactive[0].deleted_reason == "superseded"
        assert inactive[0].superseded_by == newer.id


class TestLowConfidenceContradiction:
    @pytest.mark.asyncio
    async def test_low_confidence_contradiction_keeps_both(
        self,
        memory_store: MemoryStore,
        resolver: ContradictionResolver,
        inference: FakeInferenceClient,
    ) -> None:
        """A contradiction judgment below the confidence threshold leaves both memories."""
        await memory_store.save(
            content="User lives in NYC.",
            tags=["location"],
            platform="cli",
            platform_user="alice",
        )
        await memory_store.save(
            content="User lives in LA.",
            tags=["location"],
            platform="cli",
            platform_user="alice",
        )

        inference._responses.append((True, 0.5, "city", "Maybe a contradiction."))

        result = await resolver.run("cli", "alice")

        assert result.superseded_count == 0
        assert result.examined_count == 1

        active = await memory_store.list_active_memories(
            platform="cli", platform_user="alice"
        )
        assert len(active) == 2


class TestSeparateFacts:
    @pytest.mark.asyncio
    async def test_separate_facts_are_not_contradictions(
        self,
        memory_store: MemoryStore,
        resolver: ContradictionResolver,
        inference: FakeInferenceClient,
    ) -> None:
        """Genuinely separate facts about different attributes are not contradictions."""
        await memory_store.save(
            content="User owns a home in Austin.",
            tags=["property"],
            platform="cli",
            platform_user="alice",
        )
        await memory_store.save(
            content="User owns a vacation cabin in Denver.",
            tags=["property"],
            platform="cli",
            platform_user="alice",
        )

        inference._responses.append((False, 0.2, None, None))

        result = await resolver.run("cli", "alice")

        assert result.superseded_count == 0
        assert result.examined_count == 1

        active = await memory_store.list_active_memories(
            platform="cli", platform_user="alice"
        )
        assert len(active) == 2


class TestProtectedMemory:
    @pytest.mark.asyncio
    async def test_protected_memory_never_superseded(
        self,
        memory_store: MemoryStore,
        resolver: ContradictionResolver,
        inference: FakeInferenceClient,
    ) -> None:
        """Protected memories are never sent to the LLM or superseded."""
        protected = await memory_store.save(
            content="User likes blue.",
            tags=["preference"],
            platform="cli",
            platform_user="alice",
        )
        await memory_store.pin(protected.id, pinned=True)

        await memory_store.save(
            content="User likes green.",
            tags=["preference"],
            platform="cli",
            platform_user="alice",
        )

        # The engine should not call the LLM, but provide a response just in case.
        inference._responses.append((True, 0.95, "color", "Newer wins."))

        result = await resolver.run("cli", "alice")

        assert result.superseded_count == 0
        assert result.examined_count == 0
        assert len(inference.calls) == 0

        active = await memory_store.list_active_memories(
            platform="cli", platform_user="alice"
        )
        assert len(active) == 2


class TestSupersessionReasoning:
    @pytest.mark.asyncio
    async def test_supersession_records_reasoning(
        self,
        memory_store: MemoryStore,
        resolver: ContradictionResolver,
        inference: FakeInferenceClient,
    ) -> None:
        """The superseded memory's content retains the LLM's reasoning."""
        older = await memory_store.save(
            content="User likes the color blue",
            tags=["preference"],
            platform="cli",
            platform_user="alice",
        )
        newer = await memory_store.save(
            content="User likes the color green",
            tags=["preference"],
            platform="cli",
            platform_user="alice",
        )

        reasoning = "User changed favorite color; newer fact wins."
        inference._responses.append((True, 0.95, "color", reasoning))

        await resolver.run("cli", "alice")

        inactive = await memory_store.list_inactive_memories(
            platform="cli", platform_user="alice"
        )
        assert len(inactive) == 1
        loser = inactive[0]
        assert loser.id == older.id
        assert reasoning in loser.content
        assert f"Superseded by {newer.id}" in loser.content
