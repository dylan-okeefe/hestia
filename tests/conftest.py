"""Pytest configuration for the whole test tree.

H-5 (Copilot): ``model_name == "dummy"`` is rejected unless
``HESTIA_ALLOW_DUMMY_MODEL=1``. Many unit tests build ``AppContext`` via
``make_app`` with an empty ``inference.model_name``; the app layer maps that to
``dummy`` only when this env is set so ``InferenceClient`` construction succeeds.
"""

from __future__ import annotations

import os

import pytest

from hestia.core.types import ChatResponse, ToolCall


@pytest.fixture(scope="session", autouse=True)
def _allow_dummy_model_for_tests() -> None:
    os.environ.setdefault("HESTIA_ALLOW_DUMMY_MODEL", "1")


@pytest.fixture(autouse=True)
def _clear_webhook_seen_cache() -> None:
    """Clear the webhook replay-protection cache before every test."""
    from hestia.web.routes.webhooks import _seen_signatures

    _seen_signatures.clear()


@pytest.fixture
def make_chat_response():
    """Factory for creating real ChatResponse dataclasses in tests."""

    def _factory(
        content: str = "",
        reasoning_content: str | None = None,
        tool_calls: list[ToolCall] | None = None,
        finish_reason: str = "stop",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
    ) -> ChatResponse:
        return ChatResponse(
            content=content,
            reasoning_content=reasoning_content,
            tool_calls=tool_calls or [],
            finish_reason=finish_reason,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    return _factory
