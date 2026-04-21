"""Integration tests for the Orchestrator."""

from datetime import datetime

import pytest

from hestia.artifacts.store import ArtifactStore
from hestia.context.builder import ContextBuilder
from hestia.core.types import Message
from hestia.orchestrator import Orchestrator, TurnState
from hestia.persistence.db import Database
from hestia.persistence.sessions import SessionStore
from hestia.tools.builtin.current_time import current_time
from hestia.tools.builtin.terminal import terminal
from hestia.tools.registry import ToolRegistry


class FakeInferenceClient:
    """Fake inference client for testing."""

    def __init__(self, responses=None):
        """Initialize with optional list of responses."""
        self.model_name = "fake-model"
        self.responses = responses or []
        self.call_count = 0
        self.closed = False

    async def tokenize(self, text: str) -> list[int]:
        return [0] * (len(text) // 4 + 1)

    async def count_request(self, messages, tools):
        """Simple char-based token count."""
        total = 0
        for msg in messages:
            total += 10 + len(msg.content) // 4
        for _tool in tools:
            total += 50  # Tool schema cost
        return total

    async def chat(self, messages, tools=None, slot_id=None, **kwargs):
        """Return next canned response."""
        from hestia.core.types import ChatResponse

        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response

        # Default: simple text response
        self.call_count += 1
        return ChatResponse(
            content="Test response",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )

    async def close(self):
        """Mark as closed."""
        self.closed = True

    async def health(self):
        """Return fake health."""
        return {"status": "ok"}


class FakePolicyEngine:
    """Fake policy engine for testing."""

    def should_delegate(
        self,
        session,
        task_description,
        tool_chain_length: int = 0,
        projected_tool_calls: int = 0,
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
        return 4000

    def tool_result_max_chars(self, tool_name):
        return 4000

    def reasoning_budget(self, session, iteration):
        return 2048

    def auto_approve(self, tool_name, session):
        return False


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
def fake_inference():
    """Fake inference client."""
    return FakeInferenceClient()


@pytest.fixture
def fake_policy():
    """Fake policy engine."""
    return FakePolicyEngine()


@pytest.fixture
def artifact_store(tmp_path):
    """Artifact store in temp directory."""
    return ArtifactStore(tmp_path / "artifacts")


@pytest.fixture
def tool_registry(artifact_store):
    """Tool registry with current_time tool."""
    registry = ToolRegistry(artifact_store)
    registry.register(current_time)
    registry.register(terminal)
    return registry


@pytest.fixture
def context_builder(fake_inference, fake_policy):
    """Context builder with no calibration."""
    return ContextBuilder(fake_inference, fake_policy, body_factor=1.0)


@pytest.fixture
def responses():
    """List to capture responses."""
    return []


@pytest.fixture
def respond_callback(responses):
    """Callback that captures responses."""

    async def callback(response):
        responses.append(response)

    return callback


@pytest.mark.asyncio
async def test_simple_turn_completes(
    store,
    fake_inference,
    fake_policy,
    context_builder,
    tool_registry,
    respond_callback,
):
    """A simple turn with no tool calls completes successfully."""
    from hestia.core.types import Session, SessionState, SessionTemperature

    # Create session
    session = Session(
        id="test_session",
        platform="test",
        platform_user="user",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )

    # Create orchestrator
    orchestrator = Orchestrator(
        inference=fake_inference,
        session_store=store,
        context_builder=context_builder,
        tool_registry=tool_registry,
        policy=fake_policy,
        max_iterations=10,
    )

    user_message = Message(role="user", content="Hello")

    turn = await orchestrator.process_turn(
        session=session,
        user_message=user_message,
        respond_callback=respond_callback,
    )

    assert turn.state == TurnState.DONE
    assert turn.final_response is not None
    assert turn.iterations >= 0


@pytest.mark.asyncio
async def test_turn_with_tool_calls(
    store,
    fake_policy,
    context_builder,
    tool_registry,
    respond_callback,
):
    """A turn that triggers tool calls."""
    from hestia.core.types import ChatResponse, Session, SessionState, SessionTemperature, ToolCall

    # Create inference client that returns a tool call, then a final response
    tool_call_response = ChatResponse(
        content="",
        reasoning_content=None,
        tool_calls=[ToolCall(id="call_1", name="list_tools", arguments={"tag": None})],
        finish_reason="tool_calls",
        prompt_tokens=20,
        completion_tokens=10,
        total_tokens=30,
    )
    final_response = ChatResponse(
        content="Here are your tools.",
        reasoning_content=None,
        tool_calls=[],
        finish_reason="stop",
        prompt_tokens=30,
        completion_tokens=5,
        total_tokens=35,
    )

    inference = FakeInferenceClient([tool_call_response, final_response])

    session = Session(
        id="test_session_tool",
        platform="test",
        platform_user="user",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )

    orchestrator = Orchestrator(
        inference=inference,
        session_store=store,
        context_builder=context_builder,
        tool_registry=tool_registry,
        policy=fake_policy,
        max_iterations=10,
    )

    user_message = Message(role="user", content="What tools do you have?")

    turn = await orchestrator.process_turn(
        session=session,
        user_message=user_message,
        respond_callback=respond_callback,
    )

    assert turn.state == TurnState.DONE
    assert turn.tool_calls_made >= 1
    assert turn.iterations >= 1


@pytest.mark.asyncio
async def test_turn_persisted_to_database(
    store,
    fake_inference,
    fake_policy,
    context_builder,
    tool_registry,
    respond_callback,
):
    """Turn data is persisted to the database."""
    from hestia.core.types import Session, SessionState, SessionTemperature

    session = Session(
        id="test_session_persist",
        platform="test",
        platform_user="user",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )

    orchestrator = Orchestrator(
        inference=fake_inference,
        session_store=store,
        context_builder=context_builder,
        tool_registry=tool_registry,
        policy=fake_policy,
        max_iterations=10,
    )

    user_message = Message(role="user", content="Hello")

    turn = await orchestrator.process_turn(
        session=session,
        user_message=user_message,
        respond_callback=respond_callback,
    )

    # Verify turn was persisted
    persisted_turn = await store.get_turn(turn.id)
    assert persisted_turn is not None
    assert persisted_turn.state == TurnState.DONE


@pytest.mark.asyncio
async def test_two_tool_chain_time_and_file_count(
    store,
    fake_policy,
    context_builder,
    artifact_store,
    respond_callback,
):
    """The model should chain current_time and terminal to answer a compound query.

    Query: "What time is it in Tokyo, and how many files are in /tmp?"

    Expected tool sequence:
      1. current_time(timezone="Asia/Tokyo") -> Tokyo time
      2. terminal(command="ls /tmp | wc -l") -> file count
      3. Assistant synthesizes final answer mentioning both values.
    """
    from hestia.core.types import ChatResponse, Session, SessionState, SessionTemperature, ToolCall

    # Create tool registry with both tools
    registry = ToolRegistry(artifact_store)
    registry.register(current_time)
    registry.register(terminal)

    # Mock inference to return a planned sequence
    responses = [
        # First call: model decides to call current_time
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="call_1",
                    name="call_tool",
                    arguments={
                        "name": "current_time",
                        "arguments": {"timezone": "Asia/Tokyo"},
                    },
                )
            ],
            finish_reason="tool_calls",
            prompt_tokens=20,
            completion_tokens=10,
            total_tokens=30,
        ),
        # Second call: model decides to call terminal
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="call_2",
                    name="call_tool",
                    arguments={
                        "name": "terminal",
                        "arguments": {"command": "ls /tmp | wc -l"},
                    },
                )
            ],
            finish_reason="tool_calls",
            prompt_tokens=30,
            completion_tokens=10,
            total_tokens=40,
        ),
        # Third call: model produces final answer
        ChatResponse(
            content="The time in Tokyo is 2026-04-09 22:30:00 JST, and there are 12 files in /tmp.",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=40,
            completion_tokens=20,
            total_tokens=60,
        ),
    ]
    inference = FakeInferenceClient(responses)

    # Create context builder with the fake inference
    builder = ContextBuilder(inference, fake_policy, body_factor=1.0)

    session = Session(
        id="test_session_two_tools",
        platform="test",
        platform_user="user",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )

    async def auto_approve(tool_name: str, arguments: dict) -> bool:
        return True

    orchestrator = Orchestrator(
        inference=inference,
        session_store=store,
        context_builder=builder,
        tool_registry=registry,
        policy=fake_policy,
        confirm_callback=auto_approve,  # Required: terminal has requires_confirmation=True
        max_iterations=10,
    )

    response_capture = []

    async def capture_response(text: str) -> None:
        response_capture.append(text)

    user_msg = Message(
        role="user",
        content="What time is it in Tokyo, and how many files are in /tmp?",
    )

    turn = await orchestrator.process_turn(
        session=session,
        user_message=user_msg,
        respond_callback=capture_response,
    )

    # Assertions
    assert turn.state == TurnState.DONE
    assert turn.iterations == 2  # two tool-call iterations, then final
    assert turn.tool_calls_made == 2
    assert len(response_capture) == 1
    assert "Tokyo" in response_capture[0]
    assert "12" in response_capture[0] or "files" in response_capture[0]

    # Verify the tool calls actually executed (check message history)
    messages = await store.get_messages(session.id)
    tool_messages = [m for m in messages if m.role == "tool"]
    assert len(tool_messages) == 2

    # Verify at least one tool result contains Tokyo time info
    tool_contents = [m.content for m in tool_messages]
    assert any("JST" in c or "2026" in c for c in tool_contents) or any(
        c.isdigit() for c in tool_contents
    )


@pytest.mark.asyncio
async def test_turn_fetches_message_history_at_most_once(
    store, artifact_store, fake_policy
):
    """M-2: an N-iteration turn hits SessionStore.get_messages exactly once.

    Before M-2 the orchestrator re-fetched history from the store after every
    tool-call iteration. For a two-tool turn that was 3 reads (initial + 2
    rebuilds). This test counts calls on a wrapper around SessionStore and
    asserts the rebuild-time reads are gone.
    """
    from hestia.core.types import ChatResponse, Session, SessionState, SessionTemperature, ToolCall

    class _CountingStore:
        """Transparent SessionStore wrapper that counts get_messages calls."""

        def __init__(self, inner):
            self._inner = inner
            self.get_messages_calls = 0

        def __getattr__(self, name):
            return getattr(self._inner, name)

        async def get_messages(self, session_id):
            self.get_messages_calls += 1
            return await self._inner.get_messages(session_id)

    counting_store = _CountingStore(store)

    registry = ToolRegistry(artifact_store)
    registry.register(current_time)
    registry.register(terminal)

    responses = [
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="tc1",
                    name="call_tool",
                    arguments={"name": "current_time", "arguments": {"timezone": "UTC"}},
                )
            ],
            finish_reason="tool_calls",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="tc2",
                    name="call_tool",
                    arguments={
                        "name": "terminal",
                        "arguments": {"command": "echo ok"},
                    },
                )
            ],
            finish_reason="tool_calls",
            prompt_tokens=15,
            completion_tokens=5,
            total_tokens=20,
        ),
        ChatResponse(
            content="Done.",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=20,
            completion_tokens=5,
            total_tokens=25,
        ),
    ]
    inference = FakeInferenceClient(responses)
    builder = ContextBuilder(inference, fake_policy, body_factor=1.0)

    session = Session(
        id="sess_m2",
        platform="test",
        platform_user="user",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )

    async def auto_approve(_tool, _args):
        return True

    orchestrator = Orchestrator(
        inference=inference,
        session_store=counting_store,  # type: ignore[arg-type]
        context_builder=builder,
        tool_registry=registry,
        policy=fake_policy,
        confirm_callback=auto_approve,
        max_iterations=10,
    )

    async def _noop(_text):
        return None

    turn = await orchestrator.process_turn(
        session=session, user_message=Message(role="user", content="two tools please"),
        respond_callback=_noop,
    )

    assert turn.state == TurnState.DONE
    assert turn.iterations == 2  # two tool-call iterations
    assert counting_store.get_messages_calls == 1, (
        f"Expected exactly one get_messages call per turn (M-2 invariant), "
        f"got {counting_store.get_messages_calls}"
    )
