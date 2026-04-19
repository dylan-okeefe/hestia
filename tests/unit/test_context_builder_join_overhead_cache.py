"""Unit tests for ContextBuilder._join_overhead lazy cache."""

from datetime import datetime

import pytest

from hestia.context.builder import ContextBuilder
from hestia.core.types import Message, Session, SessionState, SessionTemperature, ToolSchema
from hestia.policy.default import DefaultPolicyEngine


class CountingFakeInferenceClient:
    """Fake inference client that counts tokenize calls."""

    def __init__(self) -> None:
        self.model_name = "fake-model"
        self.tokenize_count = 0
        self.model_body_tokenize_count = 0
        self._tokenize_inputs: list[str] = []

    async def tokenize(self, text: str) -> list[int]:
        self.tokenize_count += 1
        self._tokenize_inputs.append(text)
        if '"model"' in text:
            self.model_body_tokenize_count += 1
        return [0] * (len(text) // 4 + 1)

    async def count_request(self, messages: list[Message], tools: list[ToolSchema]) -> int:
        """Simple char-based token count for testing."""
        total = 0
        for msg in messages:
            total += 10
            total += len(msg.content) // 4
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    total += len(tc.name) + len(str(tc.arguments))
        for tool in tools:
            total += len(tool.function.name) * 2
        return total


@pytest.fixture
def counting_client():
    """Counting fake inference client."""
    return CountingFakeInferenceClient()


@pytest.fixture
def policy():
    """Default policy with reasonable budget."""
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


class TestJoinOverheadCache:
    """Tests for _join_overhead lazy caching."""

    @pytest.mark.asyncio
    async def test_join_overhead_computed_once_across_builds(
        self, counting_client, policy, sample_session
    ):
        """Join overhead tokenize calls happen once total across two builds."""
        builder = ContextBuilder(counting_client, policy, body_factor=1.0)

        history = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there"),
            Message(role="user", content="How are you?"),
            Message(role="assistant", content="I am fine"),
        ]
        new_msg = Message(role="user", content="What's new?")

        await builder.build(
            sample_session, history, "You are helpful.", [], new_user_message=new_msg
        )
        after_first = counting_client.tokenize_count
        model_body_first = counting_client.model_body_tokenize_count

        await builder.build(
            sample_session, history, "You are helpful.", [], new_user_message=new_msg
        )
        after_second = counting_client.tokenize_count
        model_body_second = counting_client.model_body_tokenize_count

        # The two direct inference.tokenize calls in _compute_join_overhead
        # (single_body and combined_body) happen exactly once total.
        assert model_body_first == 2
        assert model_body_second == 2
        # Second build adds no new tokenize calls at all (everything cached).
        assert after_second == after_first
        assert builder._join_overhead is not None

    @pytest.mark.asyncio
    async def test_join_overhead_recomputed_after_too_few_messages_initially(
        self, counting_client, policy, sample_session
    ):
        """Zero from 'not enough messages' is not cached; real value cached later."""
        builder = ContextBuilder(counting_client, policy, body_factor=1.0)

        # First build: empty history and no new_user_message.
        # protected_top = [system] (1 msg), protected_bottom = [] (0 msg)
        # Total < 2 => not enough messages to measure.
        history: list[Message] = []

        await builder.build(
            sample_session, history, "You are helpful.", [], new_user_message=None
        )
        # Not enough messages to measure => stays None
        assert builder._join_overhead is None

        # Second build: 4 messages => enough to measure and cache
        history = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there"),
            Message(role="user", content="How are you?"),
            Message(role="assistant", content="I am fine"),
        ]
        new_msg = Message(role="user", content="What's new?")
        await builder.build(
            sample_session, history, "You are helpful.", [], new_user_message=new_msg
        )
        assert builder._join_overhead is not None

    @pytest.mark.asyncio
    async def test_join_overhead_value_matches_inline_implementation(
        self, counting_client, policy, sample_session
    ):
        """Cached overhead equals manual formula from tokenize records."""
        builder = ContextBuilder(counting_client, policy, body_factor=1.0)

        history = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there"),
        ]
        new_msg = Message(role="user", content="How are you?")

        await builder.build(
            sample_session, history, "You are helpful.", [], new_user_message=new_msg
        )

        # The last 3 tokenize inputs are:
        # - single_body (1 message)
        # - combined_body (2 messages)
        # - rendered _m2 for _count_tokens
        assert len(counting_client._tokenize_inputs) >= 3
        single_input = counting_client._tokenize_inputs[-3]
        combined_input = counting_client._tokenize_inputs[-2]
        m2_input = counting_client._tokenize_inputs[-1]

        single_count = len([0] * (len(single_input) // 4 + 1))
        combined_count = len([0] * (len(combined_input) // 4 + 1))
        m2_count = len([0] * (len(m2_input) // 4 + 1))
        expected = combined_count - single_count - m2_count

        assert builder._join_overhead == expected
