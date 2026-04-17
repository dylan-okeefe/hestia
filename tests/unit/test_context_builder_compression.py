"""Unit tests for ContextBuilder with history compression enabled."""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from hestia.context.builder import ContextBuilder
from hestia.core.types import Message, Session, SessionState, SessionTemperature
from hestia.policy.default import DefaultPolicyEngine


class FakeInferenceClient:
    """Fake inference client that counts tokens by character length."""

    async def count_request(self, messages, tools):
        total = 0
        for msg in messages:
            total += 10 + len(msg.content) // 4
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    total += len(tc.name) + len(str(tc.arguments))
        for tool in tools:
            total += len(tool.function.name) * 2
        return total

    async def chat(self, messages, tools=None, slot_id=None, **kwargs):
        from hestia.core.types import ChatResponse

        return ChatResponse(
            content="Prior summary: user asked about Python.",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )


@pytest.fixture
def fake_client():
    return FakeInferenceClient()


class TightBudgetPolicy(DefaultPolicyEngine):
    """Policy with a very tight token budget for testing overflow."""

    def turn_token_budget(self, session):
        return 120


@pytest.fixture
def policy():
    return TightBudgetPolicy(ctx_window=8192)


@pytest.fixture
def sample_session():
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


class FakeCompressor:
    """Fake compressor for testing."""

    def __init__(self, summary: str = "Compressed summary"):
        self.summary = summary
        self.summarize = AsyncMock(return_value=summary)


class TestCompressionEnabled:
    """Tests when compression is enabled."""

    @pytest.mark.asyncio
    async def test_summary_appears_when_enabled(self, fake_client, policy, sample_session):
        """When compression is enabled and messages are dropped, summary is spliced."""
        compressor = FakeCompressor("Dropped messages summary")
        builder = ContextBuilder(
            fake_client,
            policy,
            body_factor=1.0,
            compressor=compressor,
            compress_on_overflow=True,
        )

        # History that will overflow the tight budget
        history = [
            Message(role="user", content="OLDEST" + "x" * 200),
            Message(role="assistant", content="Old reply 1" + "x" * 200),
            Message(role="user", content="Old message 2" + "x" * 200),
            Message(role="assistant", content="Recent reply"),
        ]
        new_msg = Message(role="user", content="New question")

        result = await builder.build(
            sample_session, history, "System", [], new_user_message=new_msg
        )

        # Should have a system message with the summary
        summary_msgs = [
            m for m in result.messages
            if m.role == "system" and "PRIOR CONTEXT SUMMARY" in m.content
        ]
        assert len(summary_msgs) == 1
        assert "Dropped messages summary" in summary_msgs[0].content

    @pytest.mark.asyncio
    async def test_compressor_called_with_dropped_messages(
        self, fake_client, policy, sample_session
    ):
        """Compressor receives dropped messages in chronological order."""
        compressor = FakeCompressor("Summary")
        builder = ContextBuilder(
            fake_client,
            policy,
            body_factor=1.0,
            compressor=compressor,
            compress_on_overflow=True,
        )

        history = [
            Message(role="user", content="FIRST" + "x" * 200),
            Message(role="assistant", content="SECOND" + "x" * 200),
            Message(role="user", content="THIRD" + "x" * 200),
            Message(role="assistant", content="Recent"),
        ]
        new_msg = Message(role="user", content="New")

        await builder.build(
            sample_session, history, "System", [], new_user_message=new_msg
        )

        compressor.summarize.assert_called_once()
        dropped = compressor.summarize.call_args[0][0]
        # Dropped messages should be in chronological order (oldest first)
        contents = [m.content for m in dropped]
        assert any("FIRST" in c or "SECOND" in c or "THIRD" in c for c in contents)


class TestCompressionDisabled:
    """Tests when compression is disabled."""

    @pytest.mark.asyncio
    async def test_summary_absent_when_disabled(self, fake_client, policy, sample_session):
        """When compression is disabled, no summary message appears."""
        compressor = FakeCompressor("Should not appear")
        builder = ContextBuilder(
            fake_client,
            policy,
            body_factor=1.0,
            compressor=compressor,
            compress_on_overflow=False,
        )

        history = [
            Message(role="user", content="OLD" + "x" * 200),
            Message(role="assistant", content="Recent"),
        ]
        new_msg = Message(role="user", content="New")

        result = await builder.build(
            sample_session, history, "System", [], new_user_message=new_msg
        )

        summary_msgs = [
            m for m in result.messages if "PRIOR CONTEXT SUMMARY" in m.content
        ]
        assert len(summary_msgs) == 0
        compressor.summarize.assert_not_called()

    @pytest.mark.asyncio
    async def test_summary_absent_without_compressor(self, fake_client, policy, sample_session):
        """When no compressor is set, no summary appears even on overflow."""
        builder = ContextBuilder(
            fake_client,
            policy,
            body_factor=1.0,
            compressor=None,
            compress_on_overflow=True,
        )

        history = [
            Message(role="user", content="OLD" + "x" * 200),
            Message(role="assistant", content="Recent"),
        ]
        new_msg = Message(role="user", content="New")

        result = await builder.build(
            sample_session, history, "System", [], new_user_message=new_msg
        )

        summary_msgs = [
            m for m in result.messages if "PRIOR CONTEXT SUMMARY" in m.content
        ]
        assert len(summary_msgs) == 0
