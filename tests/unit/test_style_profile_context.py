"""Unit tests for ContextBuilder style prefix integration."""

from __future__ import annotations

import pytest

from hestia.context.builder import ContextBuilder
from hestia.core.types import Session, SessionState, SessionTemperature
from hestia.policy.default import DefaultPolicyEngine


class FakeInference:
    model_name = "fake-model"

    async def tokenize(self, text: str) -> list[int]:
        return [0] * len(text.split())

    async def count_request(self, messages, tools=None):
        return sum(len((m.content or "").split()) for m in messages)


@pytest.fixture
def builder():
    inference = FakeInference()
    policy = DefaultPolicyEngine(ctx_window=4096)
    return ContextBuilder(inference, policy)


@pytest.fixture
def session():
    return Session(
        id="s1",
        platform="cli",
        platform_user="default",
        started_at=__import__("datetime").datetime.now(),
        last_active_at=__import__("datetime").datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.HOT,
    )


@pytest.mark.asyncio
async def test_style_prefix_appended_last(builder, session):
    """Style prefix should appear after identity, memory_epoch, and skill_index."""
    builder.set_identity_prefix("[IDENTITY]")
    builder.set_memory_epoch_prefix("[MEMORY]")
    builder.set_skill_index_prefix("[SKILLS]")
    builder.set_style_prefix("[STYLE] tone: casual.")
    result = await builder.build(
        session=session,
        history=[],
        system_prompt="Base prompt",
        tools=[],
    )

    system_msg = result.messages[0]
    assert system_msg.role == "system"
    lines = system_msg.content.split("\n\n")
    assert lines == [
        "[IDENTITY]",
        "[MEMORY]",
        "[SKILLS]",
        "[STYLE] tone: casual.",
        "Base prompt",
    ]


@pytest.mark.asyncio
async def test_style_prefix_omitted_when_none(builder, session):
    """When style_prefix is None, it should not appear in the effective prompt."""
    result = await builder.build(
        session=session,
        history=[],
        system_prompt="Base prompt",
        tools=[],
    )

    system_msg = result.messages[0]
    assert "[STYLE]" not in system_msg.content
    assert system_msg.content == "Base prompt"


@pytest.mark.asyncio
async def test_style_prefix_setter(builder, session):
    """set_style_prefix should update the default style prefix."""
    builder.set_style_prefix("[STYLE] setter test.")
    result = await builder.build(
        session=session,
        history=[],
        system_prompt="Base prompt",
        tools=[],
    )

    system_msg = result.messages[0]
    assert "[STYLE] setter test." in system_msg.content
