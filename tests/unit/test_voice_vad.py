"""Tests for the stub VAD wrapper (L41)."""

from __future__ import annotations

import pytest

from hestia.voice.vad import SileroVAD


async def _chunk_stream(chunks: list[bytes]) -> None:
    """Yield chunks for the VAD segmenter."""
    for chunk in chunks:
        yield chunk


class TestSileroVAD:
    """Tests for the SileroVAD stub."""

    @pytest.mark.asyncio
    async def test_single_segment_output(self):
        """The stub should concatenate all chunks and yield one segment."""
        vad = SileroVAD()
        chunks = [b"hello", b" ", b"world"]
        segments = []
        async for segment in vad.segment(_chunk_stream(chunks)):
            segments.append(segment)

        assert len(segments) == 1
        assert segments[0] == b"hello world"

    @pytest.mark.asyncio
    async def test_empty_stream_yields_nothing(self):
        """An empty stream should produce no segments."""
        vad = SileroVAD()
        segments = []
        async for segment in vad.segment(_chunk_stream([])):
            segments.append(segment)

        assert len(segments) == 0

    @pytest.mark.asyncio
    async def test_single_chunk_stream(self):
        """A single chunk should yield one segment."""
        vad = SileroVAD()
        segments = []
        async for segment in vad.segment(_chunk_stream([b"single"])):
            segments.append(segment)

        assert len(segments) == 1
        assert segments[0] == b"single"
