"""Tests for the system-prompt rule drift detector in serve.py."""

from __future__ import annotations

from hestia.commands.serve import (
    _extract_numbered_rules,
    _missing_system_prompt_rules,
)


class TestExtractNumberedRules:
    def test_extracts_simple_rules(self) -> None:
        prompt = (
            "CRITICAL RULES:\n"
            "1. First rule.\n"
            "2. Second rule.\n"
            "3. Third rule."
        )
        rules = _extract_numbered_rules(prompt)
        assert rules == {
            1: "First rule.",
            2: "Second rule.",
            3: "Third rule.",
        }

    def test_ignores_non_numbered_lines(self) -> None:
        prompt = (
            "You are Hestia.\n"
            "CRITICAL RULES:\n"
            "1. First rule.\n"
            "Some random text.\n"
            "2. Second rule."
        )
        rules = _extract_numbered_rules(prompt)
        assert rules == {1: "First rule.", 2: "Second rule."}

    def test_ignores_lines_without_text(self) -> None:
        prompt = "1. First rule.\n2.\n3. Third rule."
        rules = _extract_numbered_rules(prompt)
        assert rules == {1: "First rule.", 3: "Third rule."}

    def test_ignores_non_numeric_labels(self) -> None:
        prompt = "A. First rule.\n1. Real rule.\n2. Another rule."
        rules = _extract_numbered_rules(prompt)
        assert rules == {1: "Real rule.", 2: "Another rule."}


class TestMissingSystemPromptRules:
    def test_no_missing_rules_when_prompts_match(self) -> None:
        prompt = (
            "CRITICAL RULES:\n"
            "1. First rule.\n"
            "2. Second rule."
        )
        assert _missing_system_prompt_rules(prompt, prompt) == {}

    def test_detects_missing_rule(self) -> None:
        default = (
            "CRITICAL RULES:\n"
            "1. First rule.\n"
            "2. Second rule.\n"
            "3. Third rule."
        )
        configured = (
            "CRITICAL RULES:\n"
            "1. First rule.\n"
            "3. Third rule."
        )
        missing = _missing_system_prompt_rules(configured, default)
        assert missing == {2: "Second rule."}

    def test_detects_multiple_missing_rules(self) -> None:
        default = (
            "CRITICAL RULES:\n"
            "1. First rule.\n"
            "2. Second rule.\n"
            "3. Third rule."
        )
        configured = "CRITICAL RULES:\n1. First rule."
        missing = _missing_system_prompt_rules(configured, default)
        assert missing == {
            2: "Second rule.",
            3: "Third rule.",
        }

    def test_extra_rules_in_configured_are_ignored(self) -> None:
        default = "CRITICAL RULES:\n1. First rule."
        configured = (
            "CRITICAL RULES:\n"
            "1. First rule.\n"
            "2. Extra rule."
        )
        assert _missing_system_prompt_rules(configured, default) == {}

    def test_reordered_rules_are_not_missing(self) -> None:
        default = (
            "CRITICAL RULES:\n"
            "1. First rule.\n"
            "2. Second rule."
        )
        configured = (
            "CRITICAL RULES:\n"
            "2. Second rule.\n"
            "1. First rule."
        )
        assert _missing_system_prompt_rules(configured, default) == {}
