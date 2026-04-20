"""Voice Activity Detection (VAD) wrapper.

L41 ships a stub that yields the full stream as one segment.  L43 (Phase B)
replaces this with real Silero-VAD segmentation.
"""

from __future__ import annotations

from collections.abc import AsyncIterator


class SileroVAD:
    """Silero-VAD wrapper.  Stub in L41 (returns the whole input as one segment).

    Phase B (L43) replaces the stub with the real VAD that segments
    by voice-activity boundaries.
    """

    async def segment(self, pcm_stream: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
        """Yield audio segments.  Stub yields the full stream as one segment."""
        buffer = b""
        async for chunk in pcm_stream:
            buffer += chunk
        if buffer:
            yield buffer
