"""Tests for the system-prompt rule drift detector in serve.py."""

from __future__ import annotations

from hestia.commands.serve import (
    _extract_numbered_rules,
    _missing_system_prompt_rules,
    _rule_heading,
)
from hestia.config import HestiaConfig


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


class TestRuleHeading:
    def test_uppercase_heading_before_colon(self) -> None:
        assert _rule_heading("MEMORY SCOPE: When persisting...") == "MEMORY SCOPE"

    def test_heading_strips_whitespace(self) -> None:
        assert _rule_heading("  FILE WRITING: write via tools") == "FILE WRITING"

    def test_no_colon_falls_back_to_full_text(self) -> None:
        assert _rule_heading("First rule.") == "First rule."

    def test_lowercase_before_colon_is_not_a_heading(self) -> None:
        assert _rule_heading("Do this: carefully") == "Do this: carefully"


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
        assert missing == {"Second rule.": ""}

    def test_detects_missing_heading_rule_and_keeps_body(self) -> None:
        default = (
            "CRITICAL RULES:\n"
            "1. FIRST: do one thing.\n"
            "2. SECOND: do another."
        )
        configured = "CRITICAL RULES:\n1. FIRST: do one thing."
        missing = _missing_system_prompt_rules(configured, default)
        assert missing == {"SECOND": "do another."}

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
            "Second rule.": "",
            "Third rule.": "",
        }

    def test_extra_rules_in_configured_are_ignored(self) -> None:
        default = "CRITICAL RULES:\n1. First rule."
        configured = (
            "CRITICAL RULES:\n"
            "1. First rule.\n"
            "2. Extra rule."
        )
        assert _missing_system_prompt_rules(configured, default) == {}

    def test_renumbered_rules_are_not_missing(self) -> None:
        # The heading, not the number, is the rule's identity — a rule that
        # moved position is fine; this is the property the 2026-08 runtime
        # drift broke under number-matching.
        default = (
            "CRITICAL RULES:\n"
            "1. FIRST: do one thing.\n"
            "2. SECOND: do another."
        )
        configured = (
            "CRITICAL RULES:\n"
            "1. SECOND: do another.\n"
            "2. FIRST: do one thing."
        )
        assert _missing_system_prompt_rules(configured, default) == {}

    def test_incident_reconstruction_memory_scope_dropped(self) -> None:
        # Reconstruct the actual 2026-08 runtime drift (card #60): every
        # number 1..N still present — USER CORRECTIONS buried after extra
        # browser/search rules at position 15, MEMORY SCOPE gone. The old
        # number-matching detector returned {} against exactly this shape.
        default = HestiaConfig().system_prompt
        rules = _extract_numbered_rules(default)
        corrections = next(t for t in rules.values() if t.startswith("USER CORRECTIONS & PREFERENCES:"))
        kept = [t for t in rules.values() if not t.startswith("MEMORY SCOPE:")]
        kept.remove(corrections)
        extras = [
            "BROWSER AUTOMATION: drive the browser via tools.",
            "WEB SEARCH: search before answering.",
        ]
        reordered = kept + extras + [corrections]
        drifted = "\n".join(f"{i}. {t}" for i, t in enumerate(reordered, start=1))

        missing = _missing_system_prompt_rules(drifted, default)
        assert "MEMORY SCOPE" in missing
        assert "USER CORRECTIONS & PREFERENCES" not in missing
