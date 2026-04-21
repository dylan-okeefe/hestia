"""Unit tests for heuristic turn detector."""

from __future__ import annotations

import pytest

from hestia.voice.turn_detector import HeuristicTurnDetector, TurnDetectorConfig


class TestHeuristicTurnDetector:
    """Tests for the rule-based turn detector."""

    @pytest.fixture
    def detector(self):
        return HeuristicTurnDetector(
            TurnDetectorConfig(
                smart_turn_threshold=0.75,
                fast_silence_ms=350,
                patient_silence_ms=4000,
                safety_timeout_ms=6000,
            )
        )

    def test_empty_transcript_never_commits(self, detector):
        assert detector.should_commit("", 10_000) == (False, 0.0)

    def test_punctuation_with_fast_silence_commits(self, detector):
        commit, conf = detector.should_commit("What's the weather?", 400)
        assert commit is True
        assert conf >= 0.75

    def test_punctuation_with_no_silence_does_not_commit(self, detector):
        commit, conf = detector.should_commit("What's the weather?", 0)
        assert commit is False
        assert conf == 0.0  # silence required even with punctuation

    def test_no_punctuation_with_fast_silence_half_confidence(self, detector):
        commit, conf = detector.should_commit("what is the weather", 400)
        assert commit is False  # 0.5 < 0.75
        assert conf == 0.5

    def test_patient_silence_commits_even_without_punctuation(self, detector):
        commit, conf = detector.should_commit("what is the weather", 4000)
        assert commit is True
        assert conf == 0.8

    def test_safety_timeout_always_commits(self, detector):
        commit, conf = detector.should_commit("uh", 6000)
        assert commit is True
        assert conf == 1.0

    def test_filler_word_extends_patience(self, detector):
        commit, conf = detector.should_commit("So, um", 400)
        assert commit is False
        assert conf == 0.1

    def test_end_of_turn_keyword_forces_commit(self, detector):
        cfg = TurnDetectorConfig(end_of_turn_keywords=("over",))
        d = HeuristicTurnDetector(cfg)
        commit, conf = d.should_commit("Requesting weather, over", 0)
        assert commit is True
        assert conf == 1.0

    def test_end_of_turn_keyword_case_insensitive(self, detector):
        cfg = TurnDetectorConfig(end_of_turn_keywords=("over",))
        d = HeuristicTurnDetector(cfg)
        commit, conf = d.should_commit("Weather report OVER", 0)
        assert commit is True
        assert conf == 1.0
