"""Unit tests for ContextBuilder prefix-layer registry."""

from __future__ import annotations

import inspect

import pytest

from hestia.context.builder import ContextBuilder
from hestia.core.types import Message, Session, SessionState, SessionTemperature
from hestia.policy.default import DefaultPolicyEngine


class FakeInference:
    def __init__(self) -> None:
        self.model_name = "fake-model"

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
async def test_layers_in_documented_order(builder, session):
    """All four prefixes appear in the documented canonical order."""
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
async def test_omitted_layer_skipped(builder, session):
    """Only identity set; no double blank lines where omitted layers would be."""
    builder.set_identity_prefix("[IDENTITY]")

    result = await builder.build(
        session=session,
        history=[],
        system_prompt="Base prompt",
        tools=[],
    )

    system_msg = result.messages[0]
    assert system_msg.role == "system"
    assert system_msg.content == "[IDENTITY]\n\nBase prompt"
    assert "\n\n\n\n" not in system_msg.content


@pytest.mark.asyncio
async def test_all_omitted_falls_through_to_system_prompt_only(builder, session):
    """No setters called; assembled prompt is exactly the input system prompt."""
    result = await builder.build(
        session=session,
        history=[],
        system_prompt="Base prompt",
        tools=[],
    )

    system_msg = result.messages[0]
    assert system_msg.role == "system"
    assert system_msg.content == "Base prompt"


def test_build_signature_no_prefix_kwargs():
    """build() no longer accepts per-call prefix overrides."""
    sig = inspect.signature(ContextBuilder.build)
    params = sig.parameters
    assert "identity_prefix" not in params
    assert "memory_epoch_prefix" not in params
    assert "skill_index_prefix" not in params
    assert "style_prefix" not in params
