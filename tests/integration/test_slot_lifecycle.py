"""Integration test for full slot lifecycle through Orchestrator."""

from typing import Any

import pytest

from hestia.artifacts.store import ArtifactStore
from hestia.context.builder import ContextBuilder
from hestia.core.types import ChatResponse, Message, SessionTemperature, ToolCall
from hestia.inference import SlotManager
from hestia.orchestrator import Orchestrator, TurnState
from hestia.persistence.db import Database
from hestia.persistence.sessions import SessionStore
from hestia.policy.default import DefaultPolicyEngine
from hestia.tools.builtin.current_time import current_time
from hestia.tools.registry import ToolRegistry


class TrackedInferenceClient:
    """Fake inference client that records all slot and chat operations."""

    def __init__(self, responses: list[ChatResponse]):
        self.model_name = "fake-model"
        self.responses = responses
        self.call_count = 0
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def tokenize(self, text: str) -> list[int]:
        return [0] * (len(text) // 4 + 1)

    async def slot_save(self, slot_id: int, filename: str) -> None:
        self.calls.append(("slot_save", (slot_id, filename)))

    async def slot_restore(self, slot_id: int, filename: str) -> None:
        self.calls.append(("slot_restore", (slot_id, filename)))

    async def slot_erase(self, slot_id: int) -> None:
        self.calls.append(("slot_erase", (slot_id,)))

    async def count_request(self, messages: list, tools: list) -> int:
        total = 0
        for msg in messages:
            total += 10 + len(msg.content) // 4
        for tool in tools:
            total += 50
        return total

    async def chat(
        self,
        messages: list[Message],
        tools: list | None = None,
        slot_id: int | None = None,
        **kwargs,
    ) -> ChatResponse:
        self.calls.append(("chat", (slot_id,)))
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response
        raise RuntimeError("No more canned responses")


@pytest.fixture
async def store(tmp_path):
    """Create a SessionStore with temp database."""
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    db = Database(db_url)
    await db.connect()
    await db.create_tables()
    store = SessionStore(db)
    yield store
    await db.close()


@pytest.fixture
def artifact_store(tmp_path):
    """Artifact store in temp directory."""
    return ArtifactStore(tmp_path / "artifacts")


@pytest.fixture
def slot_dir(tmp_path):
    """Slot directory in temp directory."""
    return tmp_path / "slots"


@pytest.fixture
def tool_registry(artifact_store):
    """Tool registry with current_time tool."""
    registry = ToolRegistry(artifact_store)
    registry.register(current_time)
    return registry


@pytest.fixture
def policy():
    """Default policy engine."""
    return DefaultPolicyEngine()


@pytest.mark.asyncio
async def test_full_slot_lifecycle_through_orchestrator(
    store, artifact_store, slot_dir, tool_registry, policy
):
    """End-to-end: cold → hot → evict → restore flow with pool_size=1."""
    # Setup: pool_size=1 forces alternating eviction

    # Session A: "What time is it?" → triggers current_time → final answer
    responses_a = [
        # First call: model requests current_time tool
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="call_1",
                    name="call_tool",
                    arguments={"name": "current_time", "arguments": {"timezone": "UTC"}},
                )
            ],
            finish_reason="tool_calls",
            prompt_tokens=20,
            completion_tokens=10,
            total_tokens=30,
        ),
        # Second call: model provides final answer
        ChatResponse(
            content="The current time is 2026-04-09 14:30:00 UTC.",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=30,
            completion_tokens=10,
            total_tokens=40,
        ),
    ]
    inference_a = TrackedInferenceClient(responses_a)

    # Session B: simple question, no tools
    responses_b = [
        ChatResponse(
            content="Hello! How can I help you today?",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
    ]
    inference_b = TrackedInferenceClient(responses_b)

    # Session A turn 2: another question
    responses_a2 = [
        ChatResponse(
            content="I'm doing well, thank you for asking!",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
    ]
    inference_a2 = TrackedInferenceClient(responses_a2)

    context_builder_a = ContextBuilder(inference_a, policy, body_factor=1.0)
    context_builder_b = ContextBuilder(inference_b, policy, body_factor=1.0)
    context_builder_a2 = ContextBuilder(inference_a2, policy, body_factor=1.0)

    # Create sessions
    session_a = await store.get_or_create_session("test", "user_a")
    session_b = await store.get_or_create_session("test", "user_b")

    # === All turns use the same SlotManager (as in real usage) ===
    # We need to share the SlotManager across orchestrators for proper eviction tracking
    shared_slot_manager = SlotManager(
        inference=inference_a,  # Will be replaced each turn
        session_store=store,
        slot_dir=slot_dir,
        pool_size=1,
    )

    # === Turn 1: Session A (cold start) ===
    # Temporarily set the inference client
    shared_slot_manager._inference = inference_a

    orchestrator_a = Orchestrator(
        inference=inference_a,
        session_store=store,
        context_builder=context_builder_a,
        tool_registry=tool_registry,
        policy=policy,
        slot_manager=shared_slot_manager,
        max_iterations=10,
    )

    responses_capture_a = []

    async def capture_a(text: str) -> None:
        responses_capture_a.append(text)

    turn_a1 = await orchestrator_a.process_turn(
        session=session_a,
        user_message=Message(role="user", content="What time is it?"),
        respond_callback=capture_a,
    )

    assert turn_a1.state == TurnState.DONE
    assert "time" in responses_capture_a[0].lower()

    # Session A should be HOT with slot 0
    session_a = await store.get_session(session_a.id)
    assert session_a.temperature == SessionTemperature.HOT
    assert session_a.slot_id == 0

    # Should have: chat (tool request), chat (final answer), slot_save (checkpoint)
    call_names_a = [c[0] for c in inference_a.calls]
    assert call_names_a.count("chat") == 2
    assert "slot_save" in call_names_a

    # === Turn 2: Session B (evicts A) ===
    # Update the SlotManager's inference client
    shared_slot_manager._inference = inference_b

    orchestrator_b = Orchestrator(
        inference=inference_b,
        session_store=store,
        context_builder=context_builder_b,
        tool_registry=tool_registry,
        policy=policy,
        slot_manager=shared_slot_manager,
        max_iterations=10,
    )

    responses_capture_b = []

    async def capture_b(text: str) -> None:
        responses_capture_b.append(text)

    turn_b = await orchestrator_b.process_turn(
        session=session_b,
        user_message=Message(role="user", content="Hello!"),
        respond_callback=capture_b,
    )

    assert turn_b.state == TurnState.DONE
    assert "hello" in responses_capture_b[0].lower()

    # Session A should now be WARM (evicted)
    session_a = await store.get_session(session_a.id)
    assert session_a.temperature == SessionTemperature.WARM
    assert session_a.slot_id is None
    assert session_a.slot_saved_path is not None

    # Session B should be HOT with slot 0
    session_b = await store.get_session(session_b.id)
    assert session_b.temperature == SessionTemperature.HOT
    assert session_b.slot_id == 0

    # Should have: slot_save (for A eviction), slot_erase (for A), chat (for B), slot_save (checkpoint for B)
    call_names_b = [c[0] for c in inference_b.calls]
    assert "chat" in call_names_b
    assert "slot_save" in call_names_b

    # === Turn 3: Session A again (restores from disk, evicts B) ===
    # Update the SlotManager's inference client
    shared_slot_manager._inference = inference_a2

    orchestrator_a2 = Orchestrator(
        inference=inference_a2,
        session_store=store,
        context_builder=context_builder_a2,
        tool_registry=tool_registry,
        policy=policy,
        slot_manager=shared_slot_manager,
        max_iterations=10,
    )

    responses_capture_a2 = []

    async def capture_a2(text: str) -> None:
        responses_capture_a2.append(text)

    turn_a2 = await orchestrator_a2.process_turn(
        session=session_a,
        user_message=Message(role="user", content="How are you?"),
        respond_callback=capture_a2,
    )

    assert turn_a2.state == TurnState.DONE
    assert "well" in responses_capture_a2[0].lower()

    # Session A should be HOT again with slot 0 (restored)
    session_a = await store.get_session(session_a.id)
    assert session_a.temperature == SessionTemperature.HOT
    assert session_a.slot_id == 0
    # slot_saved_path is set again by the final save() checkpoint

    # Session B should now be WARM (evicted)
    session_b = await store.get_session(session_b.id)
    assert session_b.temperature == SessionTemperature.WARM
    assert session_b.slot_id is None

    # Should have: slot_save (for B eviction), slot_erase (for B), slot_restore (for A), chat, slot_save (checkpoint)
    call_names_a2 = [c[0] for c in inference_a2.calls]
    assert "slot_restore" in call_names_a2
    assert "chat" in call_names_a2
    assert "slot_save" in call_names_a2
