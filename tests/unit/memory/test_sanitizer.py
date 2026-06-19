"""Unit tests for the memory write-time sanitizer."""

import pytest

from hestia.memory.sanitizer import MemorySanitizer, SanitizerResult


@pytest.fixture
def sanitizer():
    """A sanitizer with default settings."""
    return MemorySanitizer()


class TestSanitizerResult:
    def test_accept_factory(self):
        result = SanitizerResult.accept("clean content")
        assert result.accepted is True
        assert result.rejected is False
        assert result.content == "clean content"
        assert result.reason is None

    def test_reject_factory(self):
        result = SanitizerResult.reject("too short")
        assert result.accepted is False
        assert result.rejected is True
        assert result.content is None
        assert result.reason == "too short"


class TestTrivialContent:
    def test_empty_string_rejected(self, sanitizer):
        result = sanitizer.sanitize("")
        assert result.rejected
        assert "empty" in result.reason.lower()

    def test_whitespace_only_rejected(self, sanitizer):
        result = sanitizer.sanitize("   \n\t  ")
        assert result.rejected
        assert "empty" in result.reason.lower()

    def test_below_minimum_length_rejected(self, sanitizer):
        result = sanitizer.sanitize("hi")
        assert result.rejected
        assert "shorter" in result.reason.lower()

    def test_pure_punctuation_rejected(self, sanitizer):
        result = sanitizer.sanitize("!?.;: !?.;:")
        assert result.rejected
        assert "punctuation" in result.reason.lower()

    def test_repeated_filler_word_rejected(self, sanitizer):
        result = sanitizer.sanitize("um um um um um")
        assert result.rejected
        assert "filler" in result.reason.lower()

    def test_repeated_single_word_rejected(self, sanitizer):
        result = sanitizer.sanitize("hello hello hello")
        assert result.rejected
        assert "filler" in result.reason.lower()

    def test_low_vocabulary_rejected(self, sanitizer):
        result = sanitizer.sanitize("like yeah like yeah")
        assert result.rejected


class TestXmlAndToolCallContent:
    def test_tool_call_xml_rejected(self, sanitizer):
        content = "<tool_call>search_memory({\"query\": \"jobs\"})</tool_call>"
        result = sanitizer.sanitize(content)
        assert result.rejected
        assert "tool-call" in result.reason.lower()

    def test_tool_call_open_tag_rejected(self, sanitizer):
        result = sanitizer.sanitize("<tool_call>")
        assert result.rejected
        assert "tool-call" in result.reason.lower()

    def test_function_tag_rejected(self, sanitizer):
        result = sanitizer.sanitize("<function=search_memory>jobs</function>")
        assert result.rejected
        assert "tool-call" in result.reason.lower()

    def test_xml_declaration_rejected(self, sanitizer):
        result = sanitizer.sanitize('<?xml version="1.0"?><root>data</root>')
        assert result.rejected
        assert "xml" in result.reason.lower()

    def test_doctype_rejected(self, sanitizer):
        result = sanitizer.sanitize(
            "<!DOCTYPE html PUBLIC \"-//W3C//DTD XHTML 1.0 Strict//EN\">"
        )
        assert result.rejected
        assert "xml" in result.reason.lower()

    def test_unclosed_tag_rejected(self, sanitizer):
        result = sanitizer.sanitize("The user likes <b>running")
        assert result.rejected
        assert "unclosed" in result.reason.lower()

    def test_unclosed_open_bracket_rejected(self, sanitizer):
        result = sanitizer.sanitize("The user likes <b running")
        assert result.rejected
        assert "unclosed" in result.reason.lower()

    def test_balanced_html_rejected_due_to_markup_density(self, sanitizer):
        # Mostly markup with very little prose is treated as suspicious.
        result = sanitizer.sanitize("<p><b><i>hi</i></b></p>")
        assert result.rejected


class TestRawTurnDumps:
    def test_role_field_rejected(self, sanitizer):
        content = '{"role": "assistant", "content": "hello"}'
        result = sanitizer.sanitize(content)
        assert result.rejected
        assert "turn dump" in result.reason.lower()

    def test_alternating_role_markers_rejected(self, sanitizer):
        content = "user: hello\nassistant: hi\nuser: bye"
        result = sanitizer.sanitize(content)
        assert result.rejected
        assert "turn dump" in result.reason.lower()

    def test_repeated_role_marker_rejected(self, sanitizer):
        content = "assistant: first\nassistant: second"
        result = sanitizer.sanitize(content)
        assert result.rejected

    def test_user_and_assistant_labels_rejected(self, sanitizer):
        content = "User asked for jobs. Assistant replied with listings."
        result = sanitizer.sanitize(content)
        assert result.rejected


class TestAcceptedContent:
    def test_clean_prose_accepted(self, sanitizer):
        content = "The user's target role is senior backend engineer."
        result = sanitizer.sanitize(content)
        assert result.accepted
        assert result.content == content

    def test_structured_key_value_summary_accepted(self, sanitizer):
        content = (
            "Goal: find backend engineering roles.\n"
            "Criteria: remote, senior level, Python.\n"
            "Progress: reviewed 15 postings, saved 3 leads.\n"
            "Pending: follow up with two recruiters.\n"
            "Key findings: Company X and Company Y are hiring.\n"
            "Artifact paths: /tmp/jobs-leads.json"
        )
        result = sanitizer.sanitize(content)
        assert result.accepted
        assert "Goal:" in result.content

    def test_whitespace_is_normalized(self, sanitizer):
        result = sanitizer.sanitize("  Clean fact here  ")
        assert result.accepted
        assert result.content == "Clean fact here"

    def test_reasonable_length_with_punctuation_accepted(self, sanitizer):
        result = sanitizer.sanitize("User's favorite color is blue.")
        assert result.accepted


class TestConfigurableMinLength:
    def test_custom_minimum_length(self):
        sanitizer = MemorySanitizer(min_length=4)
        result = sanitizer.sanitize("hi there")
        assert result.accepted

    def test_custom_minimum_length_rejects(self):
        sanitizer = MemorySanitizer(min_length=50)
        result = sanitizer.sanitize("This is too short for the configured minimum.")
        assert result.rejected
