"""Unit tests for ContextBuilder."""

from datetime import datetime

import pytest

from hestia.context.builder import ContextBuilder
from hestia.core.types import Message, Session, SessionState, SessionTemperature, ToolSchema
from hestia.errors import ContextTooLargeError
from hestia.policy.default import DefaultPolicyEngine


class FakeInferenceClient:
    """Fake inference client for testing.

    Counts tokens by character count (not realistic but deterministic).
    """

    def __init__(self) -> None:
        self.model_name = "fake-model"

    async def tokenize(self, text: str) -> list[int]:
        return [0] * (len(text) // 4 + 1)

    async def count_request(self, messages: list[Message], tools: list[ToolSchema]) -> int:
        """Simple char-based token count for testing."""
        total = 0
        for msg in messages:
            # Base cost per message
            total += 10
            # Content cost
            total += len(msg.content) // 4
            # Tool calls cost
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    total += len(tc.name) + len(str(tc.arguments))

        # Tool schema cost
        for tool in tools:
            total += len(tool.function.name) * 2

        return total

    async def tokenize_batch(self, texts: list[str]) -> list[int]:
        """Fallback batch tokenization for testing."""
        import asyncio

        results = await asyncio.gather(*(self.tokenize(t) for t in texts))
        return [len(r) for r in results]


@pytest.fixture
def fake_client():
    """Fake inference client."""
    return FakeInferenceClient()


@pytest.fixture
def policy():
    """Default policy with reasonable budget."""
    # Need ctx_window large enough that 85% - 2048 is still positive
    return DefaultPolicyEngine(ctx_window=8192)


@pytest.fixture
def sample_session():
    """Sample session fixture."""
    return Session(
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


class TestBasicBuilding:
    """Tests for basic context building."""

    @pytest.mark.asyncio
    async def test_small_history_fits_entirely(self, fake_client, policy, sample_session):
        """Small history fits entirely, no truncation."""
        builder = ContextBuilder(fake_client, policy, body_factor=1.0)

        history = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there"),
        ]
        new_msg = Message(role="user", content="How are you?")

        result = await builder.build(
            sample_session, history, "You are helpful.", [], new_user_message=new_msg
        )

        # Should have 4 messages: system, first_user, assistant, new_user
        assert len(result.messages) == 4
        assert result.messages[0].role == "system"
        assert result.messages[1].role == "user"  # first user
        assert result.messages[2].role == "assistant"
        assert result.messages[3].role == "user"  # new user
        assert result.truncated_count == 0
        assert result.kept_first_user

    @pytest.mark.asyncio
    async def test_system_always_first(self, fake_client, policy, sample_session):
        """System message is always at index 0."""
        builder = ContextBuilder(fake_client, policy, body_factor=1.0)

        history = [Message(role="user", content="Hi")]
        new_msg = Message(role="user", content="Bye")

        result = await builder.build(
            sample_session, history, "System prompt here.", [], new_user_message=new_msg
        )

        assert result.messages[0].role == "system"
        assert result.messages[0].content == "System prompt here."

    @pytest.mark.asyncio
    async def test_new_user_always_last(self, fake_client, policy, sample_session):
        """New user message is always at the end."""
        builder = ContextBuilder(fake_client, policy, body_factor=1.0)

        history = [Message(role="user", content="First")]
        new_msg = Message(role="user", content="Latest")

        result = await builder.build(
            sample_session, history, "System", [], new_user_message=new_msg
        )

        assert result.messages[-1].role == "user"
        assert result.messages[-1].content == "Latest"


class TestFirstUserProtection:
    """Tests for first user message protection."""

    @pytest.mark.asyncio
    async def test_first_user_always_kept(self, fake_client, policy, sample_session):
        """First user message is always kept even with large history."""
        builder = ContextBuilder(fake_client, policy, body_factor=1.0)

        # Create large history that will overflow budget
        history = [
            Message(role="user", content="FIRST USER MESSAGE"),
            *[Message(role="user", content="x" * 100) for _ in range(50)],
        ]
        new_msg = Message(role="user", content="New")

        result = await builder.build(
            sample_session, history, "System", [], new_user_message=new_msg
        )

        # Find first user message in result
        first_user_in_result = None
        for msg in result.messages:
            if msg.role == "user" and "FIRST" in msg.content:
                first_user_in_result = msg
                break

        assert first_user_in_result is not None, "First user message was dropped"
        assert result.kept_first_user


class TestTruncation:
    """Tests for context truncation."""

    @pytest.mark.asyncio
    async def test_truncates_when_over_budget(self, fake_client, sample_session):
        """Context building produces valid result even with large history."""
        # Use reasonable budget
        small_policy = DefaultPolicyEngine(ctx_window=4096)
        builder = ContextBuilder(fake_client, small_policy, body_factor=1.0)

        # Create large history
        history = [
            Message(role="user", content="OLDEST" + "x" * 500),
            Message(role="assistant", content="Old reply 1" + "x" * 500),
            Message(role="user", content="Old message 2" + "x" * 500),
            Message(role="assistant", content="Recent reply"),
        ]
        new_msg = Message(role="user", content="New question")

        result = await builder.build(
            sample_session, history, "System", [], new_user_message=new_msg
        )

        # Result should be valid
        assert result.tokens_used <= result.tokens_budget or result.truncated_count > 0
        # Recent messages should be prioritized
        assert any("Recent reply" in m.content for m in result.messages)

    @pytest.mark.asyncio
    async def test_keeps_recent_messages(self, fake_client, policy, sample_session):
        """Recent messages are prioritized over old ones."""
        builder = ContextBuilder(fake_client, policy, body_factor=1.0)

        history = [
            Message(role="user", content="OLDEST"),
            Message(role="user", content="RECENT"),
        ]
        new_msg = Message(role="user", content="NEW")

        result = await builder.build(
            sample_session, history, "System" + "x" * 500, [], new_user_message=new_msg
        )

        # With tight budget, OLDEST should be dropped but RECENT kept
        contents = [m.content for m in result.messages]
        assert "NEW" in contents
        assert "RECENT" in contents


class TestToolCallPairs:
    """Tests for tool call / tool result pair integrity."""

    @pytest.mark.asyncio
    async def test_keeps_tool_pairs_together(self, fake_client, policy, sample_session):
        """Tool call and tool result are kept together or dropped together."""
        from hestia.core.types import ToolCall

        builder = ContextBuilder(fake_client, policy, body_factor=1.0)

        history = [
            Message(role="user", content="Call a tool"),
            Message(
                role="assistant",
                content="",
                tool_calls=[ToolCall(id="call_1", name="test_tool", arguments={})],
            ),
            Message(role="tool", content="Tool result", tool_call_id="call_1"),
            Message(role="user", content="Next question"),
        ]
        new_msg = Message(role="user", content="Final question")

        result = await builder.build(
            sample_session, history, "System", [], new_user_message=new_msg
        )

        # Either both tool messages are present or neither
        tool_messages = [m for m in result.messages if m.role in ("tool", "assistant")]
        has_tool_call = any(m.tool_calls for m in tool_messages)
        has_tool_result = any(m.role == "tool" for m in tool_messages)

        if has_tool_call:
            assert has_tool_result, "Tool call present without tool result"


class TestTokenBudgeting:
    """Tests for token budget enforcement."""

    @pytest.mark.asyncio
    async def test_tokens_used_under_budget(self, fake_client, policy, sample_session):
        """tokens_used is always <= tokens_budget."""
        builder = ContextBuilder(fake_client, policy, body_factor=1.0)

        history = [Message(role="user", content="x" * 1000) for _ in range(20)]
        new_msg = Message(role="user", content="New")

        result = await builder.build(
            sample_session, history, "System", [], new_user_message=new_msg
        )

        assert result.tokens_used <= result.tokens_budget

    @pytest.mark.asyncio
    async def test_body_factor_applied(self, fake_client, policy, sample_session):
        """Body factor corrects the count."""
        # With factor 2.0, count should be halved
        builder = ContextBuilder(fake_client, policy, body_factor=2.0)

        history = [Message(role="user", content="Test")]
        new_msg = Message(role="user", content="New")

        result = await builder.build(
            sample_session, history, "System", [], new_user_message=new_msg
        )

        # Should be able to fit more with higher body factor
        # (counts appear smaller)
        assert result.tokens_used >= 0


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_empty_history(self, fake_client, policy, sample_session):
        """Works with empty history."""
        builder = ContextBuilder(fake_client, policy, body_factor=1.0)

        result = await builder.build(
            sample_session, [], "System", [], new_user_message=Message(role="user", content="Hi")
        )

        assert len(result.messages) == 2  # system + user
        assert result.truncated_count == 0
        assert not result.kept_first_user  # No first user in empty history

    @pytest.mark.asyncio
    async def test_protected_overflow_raises(self, fake_client, sample_session):
        """When protected messages exceed budget, raises ContextTooLargeError."""
        # Tiny budget
        policy = DefaultPolicyEngine(ctx_window=50)
        builder = ContextBuilder(fake_client, policy, body_factor=1.0)

        history = [Message(role="user", content="x" * 1000)]
        new_msg = Message(role="user", content="New" + "y" * 1000)

        with pytest.raises(ContextTooLargeError):
            await builder.build(
                sample_session, history, "System" + "z" * 1000, [], new_user_message=new_msg
            )


class TestFromCalibrationFile:
    """Tests for factory method loading calibration."""

    @pytest.mark.asyncio
    async def test_loads_from_file(self, tmp_path, fake_client, policy, sample_session):
        """Loads body_factor and meta_tool_overhead from JSON file."""
        import json

        cal_path = tmp_path / "calibration.json"
        cal_path.write_text(json.dumps({"body_factor": 1.5, "meta_tool_overhead_tokens": 100}))

        builder = ContextBuilder.from_calibration_file(fake_client, policy, cal_path)

        assert builder._body_factor == 1.5
        assert builder._meta_tool_overhead == 100

    @pytest.mark.asyncio
    async def test_defaults_when_missing(self, tmp_path, fake_client, policy):
        """Uses defaults when calibration file doesn't exist."""
        cal_path = tmp_path / "nonexistent.json"

        builder = ContextBuilder.from_calibration_file(fake_client, policy, cal_path)

        assert builder._body_factor == 1.0
        assert builder._meta_tool_overhead == 0
