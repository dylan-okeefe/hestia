"""Vision helpers: JPEG dimension parsing and image-token estimates (L234)."""

from __future__ import annotations

import base64
import binascii
import logging

logger = logging.getLogger(__name__)

# Rough tokens-per-pixel divisor: an edge-E image costs about (E/28)^2 tokens.
# Matches the L234 spec's sanctioned estimate; used ONLY for logging and
# context-budget accounting, never for billing-style accounting.
TOKEN_EDGE_DIVISOR = 28

# Fallback when a data URL cannot be decoded for dimensions: assume the
# configured default edge (1024 px) → (1024/28)^2 ≈ 1334 tokens.
_FALLBACK_EDGE_PX = 1024

_JPEG_SOF_MARKERS = frozenset(
    {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
)


def _decode_data_url(data_url: str) -> bytes | None:
    """Return the raw bytes of a ``data:*;base64,...`` URL, or None."""
    if not data_url.startswith("data:") or ";base64," not in data_url:
        return None
    payload = data_url.split(",", 1)[1]
    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        return None


def jpeg_dimensions(data_url: str) -> tuple[int, int] | None:
    """Parse (width, height) from a base64 JPEG data URL.

    Scans JPEG markers for a Start-Of-Frame segment; returns None when the
    payload is missing, undecodable, or not a baseline/progressive JPEG.
    """
    blob = _decode_data_url(data_url)
    if blob is None or len(blob) < 4 or blob[0:2] != b"\xff\xd8":
        return None
    i = 2
    n = len(blob)
    while i + 9 <= n:
        if blob[i] != 0xFF:
            i += 1
            continue
        marker = blob[i + 1]
        # Standalone markers without a length field.
        if marker in (0x01, 0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if i + 4 > n:
            return None
        seg_len = (blob[i + 2] << 8) | blob[i + 3]
        if seg_len < 2 or i + 2 + seg_len > n:
            return None
        if marker in _JPEG_SOF_MARKERS:
            height = (blob[i + 5] << 8) | blob[i + 6]
            width = (blob[i + 7] << 8) | blob[i + 8]
            return (width, height)
        i += 2 + seg_len
    return None


def estimate_image_tokens(data_url: str) -> int:
    """Estimated token cost of one image attachment.

    (longest_edge / 28)^2, per the L234 spec. Falls back to a 1024 px edge
    estimate when dimensions cannot be parsed. This is a rough planning
    estimate — the server bills the true count.
    """
    dims = jpeg_dimensions(data_url)
    if dims is None:
        logger.debug("Could not parse JPEG dims for image token estimate; using fallback")
        edge = _FALLBACK_EDGE_PX
    else:
        edge = max(dims)
    estimate = max(1, (edge // TOKEN_EDGE_DIVISOR) ** 2)
    return estimate


def estimate_images_tokens(data_urls: list[str]) -> int:
    """Estimated token cost of a list of image attachments."""
    return sum(estimate_image_tokens(u) for u in data_urls)
