# mypy: disable-error-code="no-untyped-def"
"""Integration tests for the /compact meta-command end-to-end."""

import pytest

from hestia.app import AppContext
from hestia.commands.meta import _handle_meta_command
from hestia.config import HestiaConfig, InferenceConfig, StorageConfig
from hestia.core.types import Message, SessionTemperature
from hestia.orchestrator.mappers import message_domain_to_dto


@pytest.fixture
async def app(tmp_path):
    """AppContext with a temp database and dummy model."""
    cfg = HestiaConfig(
        storage=StorageConfig(database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db"),
        inference=InferenceConfig(model_name="dummy"),
    )
    app = AppContext(cfg)
    await app.bootstrap_db()
    yield app
    await app.close()


@pytest.fixture
async def session_store(app):
    return app.session_store


@pytest.fixture
async def message_store(app):
    return app.message_store


@pytest.mark.asyncio
async def test_compact_e2e_via_app_context(app, session_store, message_store):
    """/compact through AppContext archives, summarizes, erases slot, and flushes memory."""
    session = await session_store.get_or_create_session("cli", "testuser")

    # Seed a job-search-style conversation.
    conversation = [
        ("user", "I want a remote Python job."),
        ("assistant", "I'll help you search. Any seniority preference?"),
        ("user", "Senior level, full remote."),
        ("assistant", "I saved two alerts and found roles at Acme and Beta."),
        ("user", "Add my resume to the notes."),
        ("assistant", "Referenced resume at /home/user/resume.pdf."),
        ("user", "Show me the next steps."),
        ("assistant", "Review matches and apply by Friday."),
    ]
    for i, (role, content) in enumerate(conversation):
        await message_store.append_message(
            session.id,
            message_domain_to_dto(
                Message(role=role, content=content), session.id, idx=i
            ),
        )

    # Assign a slot so we can verify it is erased.
    await session_store.assign_slot(session.id, 0)

    # Inject a fake inference client so the real summarizer and memory flush
    # run without needing a live llama.cpp server.
    from hestia.core.types import ChatResponse

    class _FakeInference:
        model_name = "fake-model"

        async def chat(self, messages, tools=None, slot_id=None, **kwargs):
            return ChatResponse(
                content=(
                    '{"goal": "Find a remote Python job", '
                    '"criteria": "Senior level, full remote", '
                    '"progress_done": "Saved two alerts; found Acme and Beta roles", '
                    '"pending": "Review matches and apply by Friday", '
                    '"key_findings": "Resume at /home/user/resume.pdf; two promising roles", '
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

        async def close(self) -> None:
            pass

    app.__dict__["inference"] = _FakeInference()
    # Re-create the summarizer so it holds the fake inference reference; the
    # compactor cached property has not been accessed yet in this test.
    from hestia.memory.compaction_summarizer import SessionCompactionSummarizer

    app.__dict__["compaction_summarizer"] = SessionCompactionSummarizer(
        inference=app.inference,
        memory_store=app.memory_store,
        topic_store=app.topic_store,
        max_chars=app.config.compaction.summary_max_chars,
        min_messages=app.config.compaction.min_messages,
    )

    outcome = await app.compactor.compact(session.id)

    assert outcome.success
    assert outcome.archived_count == len(conversation)

    active = await message_store.get_messages(session.id)
    # summary + verbatim tail (default keeps up to 10 messages; history is 8).
    assert len(active) == 1 + len(conversation)
    assert active[0].is_handoff is True
    assert "Session compacted" in active[0].content

    refreshed = await session_store.get_session(session.id)
    assert refreshed.slot_id is None
    assert refreshed.temperature == SessionTemperature.COLD

    memories = await app.memory_store.list_memories(
        platform="cli", platform_user="testuser"
    )
    assert len(memories) == 1
    assert "Find a remote Python job" in memories[0].content


@pytest.mark.asyncio
async def test_compact_meta_command_cli(app, session_store, message_store):
    """The CLI /compact meta-command routes to the compactor."""
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

    from hestia.memory.compaction_summarizer import CompactionResult, CompactionSummary

    async def _fake_summarize(session, history, instruction=None):
        return CompactionResult(
            summary=CompactionSummary(
                goal="G",
                criteria="C",
                progress_done="D",
                pending="P",
                key_findings="K",
                artifact_paths=[],
                summary="S",
            ),
            memory_id=None,
            token_cost=5,
        )

    app.compaction_summarizer.summarize_and_store = _fake_summarize

    should_exit, returned_session = await _handle_meta_command(
        "/compact focus on goals", session, session_store, message_store, app
    )

    assert should_exit is False
    assert returned_session.id == session.id
    active = await message_store.get_messages(session.id)
    assert active[0].is_handoff is True
