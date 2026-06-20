"""Integration test for orchestrator handling of ContextTooLargeError."""


import pytest

from hestia.artifacts.store import ArtifactStore
from hestia.context.builder import ContextBuilder
from hestia.core.types import ChatResponse, Message
from hestia.memory.store import MemoryStore
from hestia.orchestrator.engine import Orchestrator
from hestia.orchestrator.handoff_service import HandoffService
from hestia.orchestrator.mappers import message_domain_to_dto
from hestia.persistence.db import Database
from hestia.persistence.failure_store import FailureStore
from hestia.persistence.message_store import MessageStore
from hestia.persistence.session_store import SessionStore
from hestia.tools.registry import ToolRegistry


class ExplodingInferenceClient:
    """Inference client that raises ContextTooLargeError on count_request."""

    model_name = "fake-model"

    async def tokenize(self, text: str) -> list[int]:
        return [0] * (len(text) // 4 + 1)

    async def tokenize_batch(self, texts: list[str]) -> list[int]:
        # Simulate a huge count that always exceeds budget
        return [99999] * len(texts)

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

    def auto_approve(self, tool_name, session, registry=None):
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
async def failure_store(db):
    store = FailureStore(db)
    await store.create_table()
    yield store


@pytest.fixture
async def memory_store(db):
    store = MemoryStore(db)
    await store.create_table()
    yield store


@pytest.fixture
async def message_store(db):
    return MessageStore(db)


@pytest.mark.asyncio
async def test_overflow_records_failure_and_warns(
    db, message_store, failure_store, memory_store
):
    """End-to-end: force context overflow, assert failure record and archive memory."""
    from pathlib import Path

    inference = ExplodingInferenceClient()
    policy = FakePolicyEngine()
    builder = ContextBuilder(inference, policy, body_factor=1.0)
    artifact_store = ArtifactStore(Path("/tmp/artifacts"))
    registry = ToolRegistry(artifact_store)

    session_store = SessionStore(
        db,
        message_store=message_store,
        memory_store=memory_store,
        inference_factory=lambda: inference,
    )
    handoff_service = HandoffService(session_store, message_store)

    orchestrator = Orchestrator(
        inference=inference,
        session_store=session_store,
        context_builder=builder,
        tool_registry=registry,
        policy=policy,
        failure_store=failure_store,
        handoff_service=handoff_service,
    )

    session = await session_store.create_session("test", "user1")

    # Add enough messages to meet min_messages for handoff
    await message_store.append_message(
        session.id, message_domain_to_dto(Message(role="user", content="Hello"), session.id, idx=0)
    )
    await message_store.append_message(
        session.id, message_domain_to_dto(Message(role="assistant", content="Hi"), session.id, idx=0)
    )
    await message_store.append_message(
        session.id, message_domain_to_dto(Message(role="user", content="Question"), session.id, idx=0)
    )
    await message_store.append_message(
        session.id, message_domain_to_dto(Message(role="assistant", content="Answer"), session.id, idx=0)
    )

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

    # Archive-time memory should exist
    memories = await memory_store.list_memories(tag="task-state")
    assert len(memories) >= 1
