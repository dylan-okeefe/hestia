"""Unit tests for the LLM near-duplicate memory merge pass (L229)."""

from __future__ import annotations

import json

import pytest

from hestia.core.inference import InferenceClient
from hestia.core.types import ChatResponse, Message
from hestia.memory.maintenance.llm_dedupe import LLMDeduper
from hestia.memory.store import MemoryStore
from hestia.persistence.db import Database


class FakeInferenceClient(InferenceClient):
    """Inference client that returns deterministic dedupe JSON responses."""

    def __init__(
        self,
        responses: list[tuple[bool, float, str | None]] | None = None,
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
        duplicate, confidence, merged_content = self._responses.pop(0)
        payload = {
            "duplicate": duplicate,
            "confidence": confidence,
            "merged_content": merged_content,
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
def deduper(memory_store, inference):
    """Create an LLMDeduper bound to the test store and fake inference."""
    return LLMDeduper(memory_store, inference)


class TestLLMConfidentDuplicateMerge:
    @pytest.mark.asyncio
    async def test_llm_confident_duplicate_is_merged(
        self, memory_store: MemoryStore, deduper: LLMDeduper, inference: FakeInferenceClient
    ) -> None:
        """A high-confidence LLM duplicate judgment results in a merge."""
        first = await memory_store.save(
            content="Alice really enjoys pizza pasta weekends daily and reads books",
            tags=["food"],
            platform="cli",
            platform_user="alice",
        )
        second = await memory_store.save(
            content="Alice really enjoys pizza pasta weekends",
            tags=["weekend"],
            platform="cli",
            platform_user="alice",
        )

        inference._responses.append(
            (True, 0.95, "Alice really enjoys pizza pasta weekends and reads books daily")
        )

        result = await deduper.run("cli", "alice")

        assert result.merged_count == 1
        assert result.examined_count == 1
        assert len(inference.calls) == 1

        active = await memory_store.list_active_memories(
            platform="cli", platform_user="alice"
        )
        assert len(active) == 1
        winner = active[0]
        assert winner.id == second.id
        assert "reads books" in winner.content
        assert set(winner.tags) == {"food", "weekend"}

        inactive = await memory_store.list_inactive_memories(
            platform="cli", platform_user="alice"
        )
        assert len(inactive) == 1
        assert inactive[0].id == first.id
        assert inactive[0].deleted_reason == "llm-deduplicated"
        assert inactive[0].superseded_by == winner.id


class TestLLMLowConfidenceDuplicate:
    @pytest.mark.asyncio
    async def test_llm_low_confidence_duplicate_is_left_alone(
        self, memory_store: MemoryStore, deduper: LLMDeduper, inference: FakeInferenceClient
    ) -> None:
        """A duplicate judgment below the confidence threshold leaves memories alone."""
        await memory_store.save(
            content="Alice really enjoys pizza pasta weekends daily and reads books",
            tags=["food"],
            platform="cli",
            platform_user="alice",
        )
        await memory_store.save(
            content="Alice really enjoys pizza pasta weekends",
            tags=["weekend"],
            platform="cli",
            platform_user="alice",
        )

        inference._responses.append((True, 0.5, None))

        result = await deduper.run("cli", "alice")

        assert result.merged_count == 0
        assert result.examined_count == 1

        active = await memory_store.list_active_memories(
            platform="cli", platform_user="alice"
        )
        assert len(active) == 2


class TestLLMNonDuplicate:
    @pytest.mark.asyncio
    async def test_llm_non_duplicate_is_left_alone(
        self, memory_store: MemoryStore, deduper: LLMDeduper, inference: FakeInferenceClient
    ) -> None:
        """A non-duplicate LLM judgment leaves memories alone."""
        await memory_store.save(
            content="Alice really enjoys pizza pasta weekends daily and reads books",
            tags=["food"],
            platform="cli",
            platform_user="alice",
        )
        await memory_store.save(
            content="Alice really enjoys pizza pasta weekends",
            tags=["weekend"],
            platform="cli",
            platform_user="alice",
        )

        inference._responses.append((False, 0.9, None))

        result = await deduper.run("cli", "alice")

        assert result.merged_count == 0
        assert result.examined_count == 1

        active = await memory_store.list_active_memories(
            platform="cli", platform_user="alice"
        )
        assert len(active) == 2


class TestProtectedMemories:
    @pytest.mark.asyncio
    async def test_protected_memories_are_skipped(
        self, memory_store: MemoryStore, deduper: LLMDeduper, inference: FakeInferenceClient
    ) -> None:
        """Protected memories are never sent to the LLM as merge candidates."""
        protected = await memory_store.save(
            content="Alice really enjoys pizza pasta weekends daily and reads books",
            tags=["food"],
            platform="cli",
            platform_user="alice",
        )
        await memory_store.pin(protected.id, pinned=True)

        await memory_store.save(
            content="Alice really enjoys pizza pasta weekends",
            tags=["weekend"],
            platform="cli",
            platform_user="alice",
        )

        # The engine should not call the LLM, but provide a response just in case.
        inference._responses.append((True, 0.95, "Merged content"))

        result = await deduper.run("cli", "alice")

        assert result.merged_count == 0
        assert result.examined_count == 0
        assert len(inference.calls) == 0

        active = await memory_store.list_active_memories(
            platform="cli", platform_user="alice"
        )
        assert len(active) == 2
