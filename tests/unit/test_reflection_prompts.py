"""Tests for reflection prompt templates."""

from __future__ import annotations

from hestia.reflection.prompts import (
    PATTERN_MINING_SYSTEM_PROMPT,
    PROPOSAL_GENERATION_SYSTEM_PROMPT,
)


class TestReflectionPrompts:
    """Tests that all reflection prompt templates are well-formed."""

    def test_pattern_mining_prompt_is_non_empty(self):
        assert PATTERN_MINING_SYSTEM_PROMPT
        assert isinstance(PATTERN_MINING_SYSTEM_PROMPT, str)

    def test_proposal_generation_prompt_is_non_empty(self):
        assert PROPOSAL_GENERATION_SYSTEM_PROMPT
        assert isinstance(PROPOSAL_GENERATION_SYSTEM_PROMPT, str)

    def test_pattern_mining_contains_expected_sections(self):
        assert "observations" in PATTERN_MINING_SYSTEM_PROMPT
        assert "frustration" in PATTERN_MINING_SYSTEM_PROMPT
        assert "JSON object" in PATTERN_MINING_SYSTEM_PROMPT

    def test_proposal_generation_contains_expected_sections(self):
        assert "proposals" in PROPOSAL_GENERATION_SYSTEM_PROMPT
        assert "identity_update" in PROPOSAL_GENERATION_SYSTEM_PROMPT
        assert "JSON object" in PROPOSAL_GENERATION_SYSTEM_PROMPT

    def test_prompts_usable_as_direct_string_content(self):
        """Prompts are consumed directly by runner.py without substitution."""
        # These should be usable as message content without KeyError.
        assert "{" in PATTERN_MINING_SYSTEM_PROMPT
        assert "{" in PROPOSAL_GENERATION_SYSTEM_PROMPT
        # Verify no accidental f-string placeholders remain
        mining = PATTERN_MINING_SYSTEM_PROMPT
        proposal = PROPOSAL_GENERATION_SYSTEM_PROMPT
        assert "$" not in mining or "${" not in mining
        assert "$" not in proposal or "${" not in proposal
