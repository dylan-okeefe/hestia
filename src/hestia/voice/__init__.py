"""Hestia voice pipeline (STT/TTS).

Importing this package does NOT load models.  Models are lazy-loaded on first
use of :func:`pipeline.get_voice_pipeline`.
"""

from hestia.voice.pipeline import VoicePipeline, get_voice_pipeline

__all__ = ["VoicePipeline", "get_voice_pipeline"]
