"""Tests for maintenance trace recording across engines."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest

from hestia.core.inference import InferenceClient
from hestia.memory.maintenance.contradictions import ContradictionResolver
from hestia.memory.maintenance.dedupe import DeterministicDeduper
from hestia.memory.maintenance.llm_dedupe import LLMDeduper
from hestia.memory.maintenance.prune import DeterministicPruner
from hestia.memory.maintenance.undo import MaintenanceUndo
from hestia.memory.store import MemoryStore
from hestia.persistence.db import Database
from hestia.persistence.maintenance_trace_store import MaintenanceTraceStore


@pytest.fixture
async def db() -> AsyncGenerator[Database, None]:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.connect()
    await database.create_tables()
    yield database
    await database.close()


@pytest.fixture
async def memory_store(db: Database) -> MemoryStore:
    store = MemoryStore(db)
    await store.create_table()
    return store


@pytest.fixture
async def trace_store(db: Database) -> MaintenanceTraceStore:
    store = MaintenanceTraceStore(db)
    await store.create_table()
    return store


@pytest.mark.asyncio
async def test_merge_records_trace(
    memory_store: MemoryStore, trace_store: MaintenanceTraceStore
) -> None:
    """A deterministic merge records a trace entry."""
    await memory_store.save(
        content="Duplicate content",
        platform="cli",
        platform_user="alice",
    )
    await memory_store.save(
        content="duplicate  content",
        platform="cli",
        platform_user="alice",
    )

    deduper = DeterministicDeduper(memory_store, trace_store=trace_store)
    await deduper.run("cli", "alice")

    actions = await trace_store.list_recent(platform="cli", platform_user="alice")
    assert len(actions) == 1
    action = actions[0]
    assert action.action == "merge"
    assert action.identity_platform == "cli"
    assert action.identity_user == "alice"
    assert action.winner_memory_id is not None
    assert len(action.loser_memory_ids) == 1
    assert action.reason == "deduplicated"


@pytest.mark.asyncio
async def test_prune_records_trace(
    memory_store: MemoryStore, trace_store: MaintenanceTraceStore
) -> None:
    """A prune soft-delete records a trace entry."""
    # Insert junk directly to bypass the write-time sanitizer.
    import uuid

    from hestia.core.clock import utcnow

    memory_id = f"mem_{uuid.uuid4().hex[:16]}"
    async with memory_store._db.engine.connect() as conn:
        await conn.execute(
            __import__("sqlalchemy", fromlist=["text"]).text(
                "INSERT INTO memory (id, content, tags, session_id, created_at, "
                "platform, platform_user, is_active, deleted_at, deleted_reason, "
                "superseded_by, is_pinned, is_user_authored, last_recalled_at) "
                "VALUES (:id, :content, :tags, :session_id, :created_at, "
                ":platform, :platform_user, :is_active, :deleted_at, :deleted_reason, "
                ":superseded_by, :is_pinned, :is_user_authored, :last_recalled_at)"
            ),
            {
                "id": memory_id,
                "content": "<tool_call>foo</tool_call>",
                "tags": "",
                "session_id": None,
                "created_at": utcnow().isoformat(),
                "platform": "cli",
                "platform_user": "alice",
                "is_active": 1,
                "deleted_at": None,
                "deleted_reason": None,
                "superseded_by": None,
                "is_pinned": 0,
                "is_user_authored": 0,
                "last_recalled_at": None,
            },
        )
        await conn.commit()

    pruner = DeterministicPruner(memory_store, trace_store=trace_store)
    await pruner.run("cli", "alice")

    actions = await trace_store.list_recent(platform="cli", platform_user="alice")
    assert len(actions) == 1
    action = actions[0]
    assert action.action == "prune"
    assert action.loser_memory_ids == [memory_id]
    assert action.reason == "junk"


@pytest.mark.asyncio
async def test_supersede_records_trace_with_reasoning(
    memory_store: MemoryStore, trace_store: MaintenanceTraceStore
) -> None:
    """A contradiction supersession records a trace with attribute and reasoning."""
    first = await memory_store.save(
        content="My favorite color is blue.",
        platform="cli",
        platform_user="alice",
    )
    second = await memory_store.save(
        content="My favorite color is red.",
        platform="cli",
        platform_user="alice",
    )

    inference = AsyncMock(spec=InferenceClient)
    inference.chat = AsyncMock(
        return_value=AsyncMock(
            content=(
                "{\"contradiction\": true, \"confidence\": 0.95, "
                "\"attribute\": \"favorite color\", \"reasoning\": \"blue vs red\"}"
            )
        )
    )

    resolver = ContradictionResolver(
        memory_store,
        inference,
        trace_store=trace_store,
        confidence_threshold=0.8,
    )
    result = await resolver.run("cli", "alice")

    assert result.superseded_count == 1
    actions = await trace_store.list_recent(platform="cli", platform_user="alice")
    assert len(actions) == 1
    action = actions[0]
    assert action.action == "supersede"
    assert action.winner_memory_id in {first.id, second.id}
    assert len(action.loser_memory_ids) == 1
    assert action.details.get("attribute") == "favorite color"
    assert action.details.get("reasoning") == "blue vs red"
    assert action.details.get("confidence") == 0.95


@pytest.mark.asyncio
async def test_llm_dedupe_records_trace(
    memory_store: MemoryStore, trace_store: MaintenanceTraceStore
) -> None:
    """An LLM dedupe merge records a trace entry with confidence."""
    first = await memory_store.save(
        content="Alice really enjoys pizza pasta weekends with friends",
        platform="cli",
        platform_user="alice",
    )
    second = await memory_store.save(
        content="Alice really enjoys pizza pasta weekends",
        platform="cli",
        platform_user="alice",
    )

    inference = AsyncMock(spec=InferenceClient)
    inference.chat = AsyncMock(
        return_value=AsyncMock(
            content=(
                "{\"duplicate\": true, \"confidence\": 0.92, "
                "\"merged_content\": \"Alice really enjoys pizza pasta weekends daily\"}"
            )
        )
    )

    deduper = LLMDeduper(
        memory_store,
        inference,
        trace_store=trace_store,
        confidence_threshold=0.8,
    )
    result = await deduper.run("cli", "alice")

    assert result.merged_count == 1
    actions = await trace_store.list_recent(platform="cli", platform_user="alice")
    assert len(actions) == 1
    action = actions[0]
    assert action.action == "merge"
    assert action.reason == "llm-deduplicated"
    assert action.details.get("confidence") == 0.92
    assert action.winner_memory_id in {first.id, second.id}
    assert len(action.loser_memory_ids) == 1


@pytest.mark.asyncio
async def test_undo_restores_losers_and_records_undo_trace(
    memory_store: MemoryStore, trace_store: MaintenanceTraceStore
) -> None:
    """Undoing a maintenance action restores losers and records an undo trace."""
    await memory_store.save(
        content="Alice likes blue.",
        platform="cli",
        platform_user="alice",
    )
    await memory_store.save(
        content="Alice likes blue",
        platform="cli",
        platform_user="alice",
    )

    deduper = DeterministicDeduper(memory_store, trace_store=trace_store)
    await deduper.run("cli", "alice")

    actions = await trace_store.list_recent(platform="cli", platform_user="alice")
    assert len(actions) == 1
    merge_action = actions[0]
    assert merge_action.action == "merge"

    undo = MaintenanceUndo(
        memory_store,
        trace_store,
        undo_retention_days=7,
    )
    result = await undo.undo(merge_action.id)

    assert result.action_id == merge_action.id
    assert result.restored_count == 1

    restored = await memory_store.get(merge_action.loser_memory_ids[0])
    assert restored is not None
    assert restored.is_active

    all_actions = await trace_store.list_recent(platform="cli", platform_user="alice")
    undo_actions = [a for a in all_actions if a.action == "undo"]
    assert len(undo_actions) == 1
    assert undo_actions[0].details.get("undone_action_id") == merge_action.id
