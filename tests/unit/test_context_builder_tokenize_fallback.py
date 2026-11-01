"""L232 §4: ContextBuilder falls back to char estimates when tokenize is unsupported."""

from datetime import UTC, datetime

import pytest

from hestia.context.builder import ContextBuilder
from hestia.core.types import Message, Session, SessionState, SessionTemperature
from hestia.policy.default import DefaultPolicyEngine


class NoTokenizeClient:
    """Duck-typed inference client that does NOT support tokenize."""

    supports_tokenize = False
    model_name = "fake-model"

    async def tokenize(self, text: str) -> list[int]:
        raise AssertionError("tokenize must not be called when supports_tokenize is False")

    async def count_request(self, messages, tools):
        total = 0
        for msg in messages:
            total += max(1, len(msg.content or "") // 4)
        return total


class TokenizeClient(NoTokenizeClient):
    """Same client but with tokenize enabled (counts 1 token per char for clarity)."""

    supports_tokenize = True

    async def tokenize(self, text: str) -> list[int]:
        return list(range(len(text)))


def _session() -> Session:
    return Session(
        id="sess",
        platform="test",
        platform_user="user",
        started_at=datetime.now(UTC),
        last_active_at=datetime.now(UTC),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )


@pytest.mark.asyncio
async def test_estimate_fallback_used_when_tokenize_unsupported():
    builder = ContextBuilder(
        inference_client=NoTokenizeClient(),
        policy=DefaultPolicyEngine(ctx_window=8192),
        body_factor=1.0,
        meta_tool_overhead=0,
    )

    result = await builder.build(
        session=_session(),
        history=[Message(role="user", content="a" * 400)],
        system_prompt="sys",
        tools=[],
    )

    # 400 chars // 4 = 100 estimated tokens for the user message alone, so
    # the total must reflect the estimate rather than a real tokenize count.
    assert result.tokens_used >= 100


@pytest.mark.asyncio
async def test_real_tokenize_used_when_supported():
    builder = ContextBuilder(
        inference_client=TokenizeClient(),
        policy=DefaultPolicyEngine(ctx_window=8192),
        body_factor=1.0,
        meta_tool_overhead=0,
    )

    result = await builder.build(
        session=_session(),
        history=[Message(role="user", content="a" * 400)],
        system_prompt="sys",
        tools=[],
    )

    # Real tokenize counts 1 token per char; the 400-char user message alone
    # costs 400+ tokens, distinguishing it from the //4 estimate.
    assert result.tokens_used >= 400
