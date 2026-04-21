"""Unit tests for verbal confirmation callback."""

from __future__ import annotations

import pytest

from hestia.platforms.voice_confirm import VoiceConfirmCallback


class TestParseDecision:
    """Tests for yes/no parsing."""

    @pytest.fixture
    def callback(self):
        # SpeakerSession is not needed for static parse tests
        return VoiceConfirmCallback(session=None)  # type: ignore[arg-type]

    def test_yes_synonyms(self, callback):
        yes_inputs = [
            "yes",
            "yeah",
            "yep",
            "sure",
            "okay",
            "ok",
            "do it",
            "go ahead",
            "confirm",
            "affirmative",
        ]
        for text in yes_inputs:
            assert callback._parse_decision(text) is True, f"failed for: {text}"

    def test_no_synonyms(self, callback):
        no_inputs = [
            "no",
            "nope",
            "nah",
            "cancel",
            "stop",
            "abort",
            "don't",
            "dont",
            "negative",
            "nevermind",
        ]
        for text in no_inputs:
            assert callback._parse_decision(text) is False, f"failed for: {text}"

    def test_unclear_returns_none(self, callback):
        assert callback._parse_decision("maybe") is None
        assert callback._parse_decision("what") is None
        assert callback._parse_decision("") is None

    def test_case_insensitive(self, callback):
        assert callback._parse_decision("YES") is True
        assert callback._parse_decision("No") is False

    def test_phrase_with_yes_embedded(self, callback):
        assert callback._parse_decision("I guess yes") is True
        assert callback._parse_decision("I said no way") is False
