"""Format the style prefix for injection into the system prompt."""
from __future__ import annotations

from typing import Any


def format_style_prefix_from_data(metrics: dict[str, Any]) -> str | None:
    """Build the [STYLE] prefix from a dict of metric values.
    Expected keys: preferred_length, formality, top_topics.
    Returns None when insufficient data.
    """
    preferred_length = metrics.get("preferred_length")
    formality = metrics.get("formality")
    top_topics = metrics.get("top_topics", [])
    if preferred_length is None and formality is None and not top_topics:
        return None
    if formality is not None and formality >= 0.15:
        label = "technical"
    elif formality is not None and formality <= 0.05:
        label = "casual"
    else:
        label = "balanced"
    parts = [f"[STYLE] Recent tone: {label}."]
    if preferred_length is not None:
        parts.append(f"Preferred response length: ~{preferred_length} tokens.")
    if top_topics:
        parts.append(f"Active topics this week: {', '.join(top_topics)}.")
    return " ".join(parts)
