"""Regression tests for real XML tool-call payloads produced by the model.

These fixtures are captured from actual failing turns. They encode the exact
output of the Qwen quant, so they are much more reliable than invented examples.
"""

from datetime import datetime
from pathlib import Path

import pytest

from hestia.core.inference import _extract_tool_calls_from_text
from hestia.core.types import Message
from hestia.orchestrator.quality import DegeneratePattern, classify_turn
from hestia.orchestrator.types import Turn


FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "regression" / "xml_tool_calls"


@pytest.mark.asyncio
async def test_unclosed_write_file_huge_is_detected_as_truncated():
    """A massive unclosed write_file XML must not parse into a tool call."""
    text = (FIXTURES / "write_file_unclosed_huge.xml").read_text(encoding="utf-8")
    calls = _extract_tool_calls_from_text(text)
    assert not calls, "Unclosed huge write_file should not produce a tool call"


def test_unclosed_write_file_short_is_detected_as_truncated():
    """Even a short unclosed write_file XML should not parse."""
    text = (FIXTURES / "write_file_unclosed.xml").read_text(encoding="utf-8")
    calls = _extract_tool_calls_from_text(text)
    assert not calls


@pytest.mark.asyncio
async def test_unclosed_write_file_huge_is_recovered_with_correction():
    """A massive unclosed write_file XML now triggers a recovery correction."""
    text = (FIXTURES / "write_file_unclosed_huge.xml").read_text(encoding="utf-8")
    turn = Turn(
        id="turn-1",
        session_id="test-session",
        state="received",  # type: ignore[arg-type]
        user_message=None,
        started_at=datetime.now(),
    )
    msg = Message(role="assistant", content=text)

    result = await classify_turn(
        turn,
        msg,
        [msg],
        ["write_file", "append_to_file"],
    )

    assert result is not None
    assert result.pattern == DegeneratePattern.TRUNCATED_WRITE_FILE
    assert "append_to_file" in result.message


def test_grep_direct_call_with_arguments_parameter():
    """A direct tool call that wraps args in <parameter=arguments>{...}</parameter>."""
    text = (FIXTURES / "grep_arguments.xml").read_text(encoding="utf-8")
    calls = _extract_tool_calls_from_text(text)
    assert len(calls) == 1
    assert calls[0].name == "grep"
    args = calls[0].arguments
    assert args["path"] == "/home/<user>/.hestia/artifacts/art_6c65504923"
    assert "builtinboston" in args["pattern"]
    assert "jobs" in args["pattern"]
