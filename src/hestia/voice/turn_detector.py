"""Turn-detection for voice conversations.

Phase B ships a heuristic implementation (punctuation + keyword + silence
thresholds).  A neural turn-detector (Pipecat Smart Turn, LiveKit Turn
Detector, etc.) can be dropped in later by swapping the class passed to
``TurnDetectorConfig``.  The protocol matters more than the specific model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class TurnDetectorConfig:
    """Configuration for turn detection."""

    smart_turn_threshold: float = 0.75
    fast_silence_ms: int = 350
    patient_silence_ms: int = 4000
    safety_timeout_ms: int = 6000
    filler_words: tuple[str, ...] = ("uh", "um", "uhh", "hmm", "wait")
    end_of_turn_keywords: tuple[str, ...] = ()


class HeuristicTurnDetector:
    """Simple rule-based turn detector.

    Rules (in priority order):

    1. **End-of-turn keywords** — trailing match forces immediate commit
       (confidence = 1.0).
    2. **Punctuation** — transcript ends with ``.?!`` → high confidence
       (0.9).  This catches clearly-complete utterances like
       "what's the weather?"
    3. **Filler words** — tail matches ``uh|um|...`` → low confidence
       (0.1).  User is still thinking; stay patient.
    4. **Silence** — the longer the silence, the higher the confidence.
       - ``fast_silence_ms`` → baseline confidence 0.5
       - ``patient_silence_ms`` → confidence 0.8
       - ``safety_timeout_ms`` → confidence 1.0 (forced commit)
    """

    def __init__(self, config: TurnDetectorConfig | None = None) -> None:
        self.cfg = config or TurnDetectorConfig()
        self._filler_re = re.compile(
            r"\b(" + "|".join(re.escape(w) for w in self.cfg.filler_words) + r")[,;:\s]*$",
            re.IGNORECASE,
        )
        if self.cfg.end_of_turn_keywords:
            self._keyword_re: re.Pattern[str] | None = re.compile(
                r"\b("
                + "|".join(re.escape(w) for w in self.cfg.end_of_turn_keywords)
                + r")[,;:\s]*$",
                re.IGNORECASE,
            )
        else:
            self._keyword_re = None

    def predict(self, partial_transcript: str, silence_ms: int) -> float:
        """Return ``P(turn_ended)`` in ``[0, 1]``.

        Args:
            partial_transcript: Current accumulated transcript.
            silence_ms: Milliseconds of continuous silence since last audio.
        """
        text = partial_transcript.strip()
        if not text:
            return 0.0

        # Rule 1 — explicit end-of-turn keyword (commits immediately)
        if self._keyword_re is not None and self._keyword_re.search(text):
            return 1.0

        # Rule 4 — safety timeout forces commit regardless of content
        if silence_ms >= self.cfg.safety_timeout_ms:
            return 1.0

        # Rule 3 — filler words at tail (still thinking)
        if self._filler_re.search(text):
            return 0.1

        # Without even fast silence, we never commit.
        if silence_ms < self.cfg.fast_silence_ms:
            return 0.0

        # At or past fast_silence_ms — combine punctuation + silence ramp
        silence_conf = self._silence_confidence(silence_ms)
        punctuation_conf = 0.9 if text[-1] in ".?!" else 0.5
        return max(punctuation_conf, silence_conf)

    def _silence_confidence(self, silence_ms: int) -> float:
        if silence_ms >= self.cfg.patient_silence_ms:
            return 0.8
        if silence_ms >= self.cfg.fast_silence_ms:
            return 0.5
        return 0.0

    def should_commit(
        self, partial_transcript: str, silence_ms: int
    ) -> tuple[bool, float]:
        """Convenience wrapper: returns ``(should_commit, confidence)``.

        Commit when confidence ≥ ``smart_turn_threshold``.
        """
        conf = self.predict(partial_transcript, silence_ms)
        return conf >= self.cfg.smart_turn_threshold, conf
