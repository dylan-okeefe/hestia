"""Unit tests for SessionHandoffSummarizer."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.config import HandoffConfig
from hestia.core.types import ChatResponse, Message, Session, SessionState, SessionTemperature
from hestia.memory.handoff import HandoffResult, SessionHandoffSummarizer


@pytest.fixture
def mock_inference():
    """Fake inference client."""
    client = MagicMock()
    client.chat = AsyncMock()
    return client


@pytest.fixture
def mock_memory_store():
    """Fake memory store."""
    store = MagicMock()
    store.save = AsyncMock(return_value=MagicMock(id="mem_123"))
    return store


@pytest.fixture
def sample_session():
    return Session(
        id="sess_1",
        platform="test",
        platform_user="user1",
        started_at=MagicMock(),
        last_active_at=MagicMock(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )


class TestHappyPath:
    """Tests for the normal handoff summarization flow."""

    @pytest.mark.asyncio
    async def test_summarizes_and_stores(self, mock_inference, mock_memory_store, sample_session):
        """Happy path: summary generated and stored."""
        mock_inference.chat.return_value = ChatResponse(
            content="Discussed project planning and decided on Python.",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )

        summarizer = SessionHandoffSummarizer(
            inference=mock_inference,
            memory_store=mock_memory_store,
            max_chars=350,
            min_messages=4,
        )

        history = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi"),
            Message(role="user", content="Let's plan"),
            Message(role="assistant", content="Sure"),
            Message(role="user", content="Python?"),
            Message(role="assistant", content="Yes"),
            Message(role="user", content="Great"),
            Message(role="assistant", content="Indeed"),
        ]

        result = await summarizer.summarize_and_store(sample_session, history)

        assert isinstance(result, HandoffResult)
        assert result.summary == "Discussed project planning and decided on Python."
        assert result.memory_id == "mem_123"
        assert result.token_cost == 15

        mock_memory_store.save.assert_called_once()
        call_kwargs = mock_memory_store.save.call_args.kwargs
        assert call_kwargs["tags"] == ["handoff", "test"]
        assert call_kwargs["session_id"] == "sess_1"


class TestSkipConditions:
    """Tests for when summarization is skipped."""

    @pytest.mark.asyncio
    async def test_skip_short_session(self, mock_inference, mock_memory_store, sample_session):
        """Sessions with fewer than min_messages user turns are skipped."""
        summarizer = SessionHandoffSummarizer(
            inference=mock_inference,
            memory_store=mock_memory_store,
            min_messages=4,
        )

        history = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi"),
            Message(role="user", content="Bye"),
        ]

        result = await summarizer.summarize_and_store(sample_session, history)
        assert result is None
        mock_inference.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_response_returns_none(self, mock_inference, mock_memory_store, sample_session):
        """If the model returns an empty summary, return None."""
        mock_inference.chat.return_value = ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=0,
            total_tokens=10,
        )

        summarizer = SessionHandoffSummarizer(
            inference=mock_inference,
            memory_store=mock_memory_store,
        )

        history = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi"),
            Message(role="user", content="Let's plan"),
            Message(role="assistant", content="Sure"),
        ]

        result = await summarizer.summarize_and_store(sample_session, history)
        assert result is None
        mock_memory_store.save.assert_not_called()


class TestTruncation:
    """Tests for summary truncation."""

    @pytest.mark.asyncio
    async def test_oversize_truncated(self, mock_inference, mock_memory_store, sample_session):
        """Summaries longer than max_chars are truncated with an ellipsis."""
        long_summary = "A" * 400
        mock_inference.chat.return_value = ChatResponse(
            content=long_summary,
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )

        summarizer = SessionHandoffSummarizer(
            inference=mock_inference,
            memory_store=mock_memory_store,
            max_chars=350,
        )

        history = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi"),
            Message(role="user", content="Let's plan"),
            Message(role="assistant", content="Sure"),
            Message(role="user", content="More"),
            Message(role="assistant", content="Ok"),
            Message(role="user", content="Even more"),
            Message(role="assistant", content="Yep"),
        ]

        result = await summarizer.summarize_and_store(sample_session, history)
        assert result is not None
        assert len(result.summary) == 351  # 350 chars + ellipsis
        assert result.summary.endswith("…")


class TestMemoryRecordShape:
    """Tests for the shape of the stored memory record."""

    @pytest.mark.asyncio
    async def test_tags_include_handoff_and_platform(self, mock_inference, mock_memory_store, sample_session):
        """Memory tags must include 'handoff' and the session platform."""
        mock_inference.chat.return_value = ChatResponse(
            content="Summary here",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )

        summarizer = SessionHandoffSummarizer(
            inference=mock_inference,
            memory_store=mock_memory_store,
        )

        history = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi"),
            Message(role="user", content="Let's plan"),
            Message(role="assistant", content="Sure"),
            Message(role="user", content="More"),
            Message(role="assistant", content="Ok"),
            Message(role="user", content="Even more"),
            Message(role="assistant", content="Yep"),
        ]

        await summarizer.summarize_and_store(sample_session, history)

        mock_memory_store.save.assert_called_once()
        tags = mock_memory_store.save.call_args.kwargs["tags"]
        assert "handoff" in tags
        assert "test" in tags
