"""Integration test for orchestrator handling of ContextTooLargeError."""


import pytest

from hestia.artifacts.store import ArtifactStore
from hestia.context.builder import ContextBuilder
from hestia.core.types import ChatResponse, Message
from hestia.memory.handoff import SessionHandoffSummarizer
from hestia.memory.store import MemoryStore
from hestia.orchestrator.engine import Orchestrator
from hestia.persistence.db import Database
from hestia.persistence.failure_store import FailureStore
from hestia.persistence.sessions import SessionStore
from hestia.tools.registry import ToolRegistry


class ExplodingInferenceClient:
    """Inference client that raises ContextTooLargeError on count_request."""

    model_name = "fake-model"

    async def tokenize(self, text: str) -> list[int]:
        return [0] * (len(text) // 4 + 1)

    async def count_request(self, messages, tools):
        # Simulate a huge count that always exceeds budget
        return 99999

    async def chat(self, messages, tools=None, slot_id=None, **kwargs):
        return ChatResponse(
            content="Summary of conversation",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )

    async def close(self):
        pass


class FakePolicyEngine:
    def should_delegate(
        self, session, task_description, tool_chain_length=0, projected_tool_calls=0
    ):
        return False

    def should_compress(self, session, tokens_used, tokens_budget):
        return False

    def retry_after_error(self, error, attempt):
        from hestia.policy.engine import RetryAction, RetryDecision
        return RetryDecision(action=RetryAction.FAIL)

    def filter_tools(self, session, tool_names, registry):
        return tool_names

    def turn_token_budget(self, session):
        return 100

    def tool_result_max_chars(self, tool_name):
        return 4000

    def reasoning_budget(self, session, iteration):
        return 2048

    def auto_approve(self, tool_name, session):
        return False


@pytest.fixture
async def db(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    database = Database(db_url)
    await database.connect()
    await database.create_tables()
    yield database
    await database.close()


@pytest.fixture
async def session_store(db):
    store = SessionStore(db)
    yield store


@pytest.fixture
async def failure_store(db):
    store = FailureStore(db)
    await store.create_table()
    yield store


@pytest.fixture
async def memory_store(db):
    store = MemoryStore(db)
    await store.create_table()
    yield store


@pytest.mark.asyncio
async def test_overflow_records_failure_and_warns(session_store, failure_store, memory_store):
    """End-to-end: force context overflow, assert failure record and handoff summary."""
    from pathlib import Path

    inference = ExplodingInferenceClient()
    policy = FakePolicyEngine()
    builder = ContextBuilder(inference, policy, body_factor=1.0)
    artifact_store = ArtifactStore(Path("/tmp/artifacts"))
    registry = ToolRegistry(artifact_store)

    summarizer = SessionHandoffSummarizer(
        inference=inference,
        memory_store=memory_store,
        min_messages=2,
    )

    orchestrator = Orchestrator(
        inference=inference,
        session_store=session_store,
        context_builder=builder,
        tool_registry=registry,
        policy=policy,
        failure_store=failure_store,
        handoff_summarizer=summarizer,
    )

    session = await session_store.create_session("test", "user1")

    # Add enough messages to meet min_messages for handoff
    await session_store.append_message(session.id, Message(role="user", content="Hello"))
    await session_store.append_message(session.id, Message(role="assistant", content="Hi"))
    await session_store.append_message(session.id, Message(role="user", content="Question"))
    await session_store.append_message(session.id, Message(role="assistant", content="Answer"))

    responses = []

    async def respond_callback(text):
        responses.append(text)

    user_message = Message(role="user", content="Trigger overflow")

    turn = await orchestrator.process_turn(
        session=session,
        user_message=user_message,
        respond_callback=respond_callback,
    )

    # Turn should be FAILED
    from hestia.orchestrator.types import TurnState
    assert turn.state == TurnState.FAILED
    assert "context budget" in turn.error.lower() or "protected context" in turn.error.lower()

    # Response callback should have been called with warning
    assert len(responses) == 1
    assert "context budget" in responses[0]
    assert "100" in responses[0]

    # Failure record should exist
    failures = await failure_store.list_recent(limit=10)
    assert len(failures) == 1
    assert failures[0].failure_class == "context_overflow"
    assert failures[0].session_id == session.id

    # Handoff summary should exist
    memories = await memory_store.list_memories(tag="handoff")
    assert len(memories) >= 1
