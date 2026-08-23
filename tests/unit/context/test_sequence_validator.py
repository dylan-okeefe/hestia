"""Tests for chat-template sequence validation."""

import logging

from hestia.context.sequence_validator import validate_chat_template_sequence
from hestia.core.types import Message, ToolCall


class TestSequenceValidator:
    """Tests for validate_chat_template_sequence."""

    def test_adjacent_assistant_messages_are_repaired(self, caplog):
        """Repeated assistant turns are collapsed to the first one."""
        messages = [
            Message(role="user", content="hello"),
            Message(role="assistant", content="first"),
            Message(role="assistant", content="second"),
            Message(role="assistant", content="third"),
        ]

        with caplog.at_level(logging.WARNING, logger="hestia.context.sequence_validator"):
            result = validate_chat_template_sequence(messages)

        assert [m.role for m in result] == ["user", "assistant"]
        assert result[1].content == "first"
        assert "Dropping adjacent assistant message" in caplog.text

    def test_orphan_tool_messages_are_dropped(self, caplog):
        """Tool results without a matching preceding assistant call are dropped,
        and the assistant's own unanswered call gets a synthetic result (BUG-019)."""
        messages = [
            Message(role="user", content="run tool"),
            Message(
                role="assistant",
                content="calling tool",
                tool_calls=[ToolCall(id="tc-1", name="search", arguments={"q": "x"})],
            ),
            Message(role="tool", content="wrong result", tool_call_id="tc-99"),
            Message(role="tool", content="no assistant result", tool_call_id="tc-2"),
        ]

        with caplog.at_level(logging.WARNING, logger="hestia.context.sequence_validator"):
            result = validate_chat_template_sequence(messages)

        assert [(m.role, m.tool_call_id) for m in result] == [
            ("user", None),
            ("assistant", None),
            ("tool", "tc-1"),  # synthesized filler for the unanswered call
        ]
        assert result[2].content.startswith("[turn interrupted")
        assert caplog.text.count("Dropping orphan tool result") == 2

    def test_dangling_assistant_gets_synthetic_tool_result(self, caplog):
        """BUG-019: a crash between persisting assistant(tool_calls=...) and its
        tool results must not brick strict-template sessions; a filler result
        is synthesized so the sequence stays valid."""
        messages = [
            Message(role="user", content="go"),
            Message(
                role="assistant",
                content="calling",
                tool_calls=[
                    ToolCall(id="tc-a", name="t", arguments={}),
                    ToolCall(id="tc-b", name="t", arguments={}),
                ],
            ),
        ]

        result = validate_chat_template_sequence(messages)

        assert [m.role for m in result] == ["user", "assistant", "tool", "tool"]
        assert {m.tool_call_id for m in result[2:]} == {"tc-a", "tc-b"}
        assert all(m.content.startswith("[turn interrupted") for m in result[2:])

    def test_tool_at_start_is_dropped(self, caplog):
        """A tool result appearing before any assistant is an orphan."""
        messages = [
            Message(role="tool", content="orphan", tool_call_id="tc-1"),
            Message(role="user", content="hello"),
        ]

        with caplog.at_level(logging.WARNING, logger="hestia.context.sequence_validator"):
            result = validate_chat_template_sequence(messages)

        assert [m.role for m in result] == ["user"]
        assert "Dropping orphan tool result" in caplog.text

    def test_valid_sequence_passes_untouched(self, caplog):
        """A well-formed assistant/tool/user/assistant sequence is preserved."""
        messages = [
            Message(role="system", content="sys"),
            Message(role="user", content="hello"),
            Message(
                role="assistant",
                content="calling tool",
                tool_calls=[ToolCall(id="tc-1", name="search", arguments={"q": "x"})],
            ),
            Message(role="tool", content="result", tool_call_id="tc-1"),
            Message(role="user", content="thanks"),
            Message(role="assistant", content="you're welcome"),
        ]

        with caplog.at_level(logging.WARNING, logger="hestia.context.sequence_validator"):
            result = validate_chat_template_sequence(messages)

        assert result == messages
        assert not caplog.records

    def test_drop_adjacent_assistant_makes_following_tool_orphan(self, caplog):
        """If an assistant is dropped, its tool results become orphans too."""
        messages = [
            Message(role="user", content="hello"),
            Message(
                role="assistant",
                content="first",
                tool_calls=[ToolCall(id="tc-1", name="search", arguments={})],
            ),
            Message(role="assistant", content="second"),
            Message(role="tool", content="result for second", tool_call_id="tc-2"),
        ]

        with caplog.at_level(logging.WARNING, logger="hestia.context.sequence_validator"):
            result = validate_chat_template_sequence(messages)

        assert [m.role for m in result] == ["user", "assistant", "tool"]
        assert result[1].content == "first"
        # The dropped second assistant never answered tc-1 on "first"; the
        # filler keeps the sequence template-valid (BUG-019).
        assert result[2].tool_call_id == "tc-1"
        assert "Dropping adjacent assistant message" in caplog.text
        assert "Dropping orphan tool result" in caplog.text

    def test_dropped_messages_are_logged(self, caplog):
        """Every dropped message produces a loud log line."""
        messages = [
            Message(role="user", content="hello"),
            Message(role="assistant", content="a1"),
            Message(role="assistant", content="a2"),
            Message(role="tool", content="orphan", tool_call_id="tc-x"),
        ]

        with caplog.at_level(logging.WARNING, logger="hestia.context.sequence_validator"):
            validate_chat_template_sequence(messages)

        dropped_logs = [
            r for r in caplog.records if r.levelno == logging.WARNING and "Dropping" in r.message
        ]
        assert len(dropped_logs) == 2
