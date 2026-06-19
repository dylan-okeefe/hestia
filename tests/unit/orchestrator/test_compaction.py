"""Unit tests for the /compact orchestration."""

import pytest

from hestia.config import CompactionConfig
from hestia.core.types import ChatResponse, Message, SessionTemperature
from hestia.inference.slot_manager import SlotManager
from hestia.memory.compaction_summarizer import SessionCompactionSummarizer
from hestia.memory.store import MemoryStore
from hestia.orchestrator.compaction import SessionCompactor
from hestia.orchestrator.lock import SessionLockManager
from hestia.orchestrator.mappers import message_domain_to_dto
from hestia.persistence.db import Database
from hestia.persistence.message_store import MessageStore
from hestia.persistence.session_store import SessionStore


@pytest.fixture
async def db(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    db = Database(db_url)
    await db.connect()
    await db.create_tables()
    yield db
    await db.close()


@pytest.fixture
async def session_store(db):
    return SessionStore(db)


@pytest.fixture
async def message_store(db):
    return MessageStore(db)


@pytest.fixture
async def memory_store(db):
    ms = MemoryStore(db)
    await ms.create_table()
    return ms


@pytest.fixture
def fake_inference():
    """Fake inference that returns a canned structured summary."""

    class _FakeInference:
        def __init__(self):
            self.model_name = "fake-model"
            self.calls = []

        async def chat(self, messages, tools=None, slot_id=None, **kwargs):
            self.calls.append(messages)
            return ChatResponse(
                content=(
                    '{"goal": "Find a remote Python job", '
                    '"criteria": "remote, Python, senior level", '
                    '"progress_done": "Searched listings and saved two alerts", '
                    '"pending": "Review matches and apply", '
                    '"key_findings": "Two promising roles at Acme and Beta", '
                    '"artifact_paths": ["art_abc123def4"], '
                    '"summary": "Job search in progress with two saved alerts."}'
                ),
                reasoning_content=None,
                tool_calls=[],
                finish_reason="stop",
                prompt_tokens=50,
                completion_tokens=30,
                total_tokens=80,
            )

        async def slot_erase(self, slot_id: int) -> None:
            pass

        async def slot_save(self, slot_id: int, filename: str) -> None:
            pass

        async def slot_restore(self, slot_id: int, filename: str) -> None:
            pass

    return _FakeInference()


@pytest.fixture
def summarizer(fake_inference, memory_store):
    return SessionCompactionSummarizer(
        inference=fake_inference,
        memory_store=memory_store,
        max_chars=1000,
        min_messages=2,
    )


@pytest.fixture
def slot_manager(tmp_path, fake_inference, session_store):
    return SlotManager(
        inference=fake_inference,
        session_store=session_store,
        slot_dir=tmp_path / "slots",
        pool_size=2,
    )


@pytest.fixture
def lock_manager():
    return SessionLockManager()


@pytest.fixture
def compactor(session_store, message_store, slot_manager, summarizer, lock_manager):
    return SessionCompactor(
        session_store=session_store,
        message_store=message_store,
        slot_manager=slot_manager,
        summarizer=summarizer,
        lock_manager=lock_manager,
        config=CompactionConfig(enabled=True, verbatim_turns=2, min_messages=2),
    )


@pytest.mark.asyncio
async def test_compact_replaces_history_with_summary_and_tail(
    session_store, message_store, compactor
):
    """Compaction archives originals and leaves [summary + verbatim tail]."""
    session = await session_store.get_or_create_session("cli", "testuser")
    for i in range(6):
        await message_store.append_message(
            session.id,
            message_domain_to_dto(
                Message(role="user" if i % 2 == 0 else "assistant", content=f"msg{i}"),
                session.id,
                idx=i,
            ),
        )

    outcome = await compactor.compact(session.id)

    assert outcome.success
    assert outcome.archived_count == 6

    active = await message_store.get_messages(session.id)
    assert len(active) == 1 + 2 * 2  # summary + 2 verbatim turns
    assert active[0].is_handoff is True
    assert "[Session compacted" in active[0].content
    assert "Find a remote Python job" in active[0].content


@pytest.mark.asyncio
async def test_compact_archives_originals_recoverable(
    session_store, message_store, compactor, db
):
    """Original messages are copied to compaction_archive before replacement."""
    session = await session_store.get_or_create_session("cli", "testuser")
    for i in range(4):
        await message_store.append_message(
            session.id,
            message_domain_to_dto(
                Message(role="user" if i % 2 == 0 else "assistant", content=f"original{i}"),
                session.id,
                idx=i,
            ),
        )

    await compactor.compact(session.id)

    import sqlalchemy as sa

    from hestia.persistence.schema import compaction_archive

    async with db.engine.connect() as conn:
        result = await conn.execute(
            sa.select(compaction_archive).where(compaction_archive.c.session_id == session.id)
        )
        rows = result.fetchall()

    assert len(rows) == 4
    contents = {row.content for row in rows}
    assert all(f"original{i}" in contents for i in range(4))


@pytest.mark.asyncio
async def test_compact_erases_slot(session_store, message_store, compactor):
    """Compaction erases the session's KV slot and demotes to COLD."""
    session = await session_store.get_or_create_session("cli", "testuser")
    # Assign a slot first.
    await session_store.assign_slot(session.id, 0)
    for i in range(4):
        await message_store.append_message(
            session.id,
            message_domain_to_dto(
                Message(role="user" if i % 2 == 0 else "assistant", content=f"msg{i}"),
                session.id,
                idx=i,
            ),
        )

    outcome = await compactor.compact(session.id)

    assert outcome.success
    refreshed = await session_store.get_session(session.id)
    assert refreshed.slot_id is None
    assert refreshed.temperature == SessionTemperature.COLD


@pytest.mark.asyncio
async def test_compact_refuses_while_locked(
    session_store, message_store, compactor, lock_manager
):
    """Compaction returns a refusal when the session lock is held."""
    session = await session_store.get_or_create_session("cli", "testuser")
    for i in range(4):
        await message_store.append_message(
            session.id,
            message_domain_to_dto(
                Message(role="user" if i % 2 == 0 else "assistant", content=f"msg{i}"),
                session.id,
                idx=i,
            ),
        )

    lock = await lock_manager.acquire(session.id)
    async with lock:
        outcome = await compactor.compact(session.id)

    assert not outcome.success
    assert "turn is currently running" in outcome.message


@pytest.mark.asyncio
async def test_compact_disabled_config(session_store, message_store):
    """Compaction is a no-op when disabled."""
    disabled = SessionCompactor(
        session_store=session_store,
        message_store=message_store,
        slot_manager=None,
        summarizer=None,
        lock_manager=SessionLockManager(),
        config=CompactionConfig(enabled=False),
    )
    session = await session_store.get_or_create_session("cli", "testuser")
    outcome = await disabled.compact(session.id)
    assert not outcome.success
    assert "disabled" in outcome.message


@pytest.mark.asyncio
async def test_compact_flushes_task_state_memory(
    session_store, message_store, compactor, memory_store
):
    """Compaction writes structured task-state fields to memory."""
    session = await session_store.get_or_create_session("cli", "testuser")
    for i in range(4):
        await message_store.append_message(
            session.id,
            message_domain_to_dto(
                Message(role="user" if i % 2 == 0 else "assistant", content=f"msg{i}"),
                session.id,
                idx=i,
            ),
        )

    outcome = await compactor.compact(session.id)

    assert outcome.success
    memories = await memory_store.list_memories(
        platform="cli",
        platform_user="testuser",
    )
    assert len(memories) == 1
    assert "Find a remote Python job" in memories[0].content
    assert "compaction" in memories[0].tags


@pytest.mark.asyncio
async def test_compact_dedups_repeat_flush(
    session_store, message_store, compactor, memory_store
):
    """Running /compact twice with identical content dedupes the memory flush."""
    session = await session_store.get_or_create_session("cli", "testuser")
    for i in range(4):
        await message_store.append_message(
            session.id,
            message_domain_to_dto(
                Message(role="user" if i % 2 == 0 else "assistant", content=f"msg{i}"),
                session.id,
                idx=i,
            ),
        )

    await compactor.compact(session.id)
    # Re-seed messages so the second compaction runs.
    for i in range(4, 8):
        await message_store.append_message(
            session.id,
            message_domain_to_dto(
                Message(role="user" if i % 2 == 0 else "assistant", content=f"msg{i}"),
                session.id,
                idx=i,
            ),
        )
    await compactor.compact(session.id)

    memories = await memory_store.list_memories(
        platform="cli",
        platform_user="testuser",
    )
    assert len(memories) == 1


@pytest.mark.asyncio
async def test_compact_instruction_passed_to_summarizer(
    session_store, message_store, compactor, fake_inference
):
    """/compact <instruction> forwards the instruction to the summarizer prompt."""
    session = await session_store.get_or_create_session("cli", "testuser")
    for i in range(4):
        await message_store.append_message(
            session.id,
            message_domain_to_dto(
                Message(role="user" if i % 2 == 0 else "assistant", content=f"msg{i}"),
                session.id,
                idx=i,
            ),
        )

    await compactor.compact(session.id, instruction="keep the job criteria")

    system_msg = fake_inference.calls[0][0]
    assert "keep the job criteria" in system_msg.content


@pytest.mark.asyncio
async def test_compact_summarizer_messages_end_with_user(
    session_store, message_store, compactor, fake_inference
):
    """The summarizer prompt must end with a user message so the model API accepts it."""
    session = await session_store.get_or_create_session("cli", "testuser")
    for i in range(4):
        await message_store.append_message(
            session.id,
            message_domain_to_dto(
                Message(role="user" if i % 2 == 0 else "assistant", content=f"msg{i}"),
                session.id,
                idx=i,
            ),
        )

    await compactor.compact(session.id)

    messages = fake_inference.calls[0]
    assert messages[-1].role == "user"
    assert "Summarize the task state as JSON" in messages[-1].content


@pytest.mark.asyncio
async def test_compact_too_short(session_store, message_store, compactor):
    """Compaction refuses when there are too few messages."""
    session = await session_store.get_or_create_session("cli", "testuser")
    await message_store.append_message(
        session.id,
        message_domain_to_dto(
            Message(role="user", content="hello"),
            session.id,
            idx=0,
        ),
    )

    outcome = await compactor.compact(session.id)

    assert not outcome.success
    assert "Not enough history" in outcome.message
