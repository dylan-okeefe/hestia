"""Format the style prefix for injection into the system prompt."""

from __future__ import annotations

import json
from typing import Any

from hestia.style.store import StyleProfileStore


def format_style_prefix(
    store: StyleProfileStore,
    platform: str,
    platform_user: str,
    min_turns: int = 20,
) -> str | None:
    """Build the [STYLE] prefix block if enough data exists.

    Returns None when the profile is below activation threshold or
    no metrics have been computed yet.
    """
    # We can't async here; callers must pre-fetch metrics.  Instead,
    # provide a helper that works on a plain dict of metric values.
    raise RuntimeError("Use format_style_prefix_from_data() with pre-fetched metrics.")


def format_style_prefix_from_data(metrics: dict[str, Any]) -> str | None:
    """Build the [STYLE] prefix from a dict of metric values.

    Expected keys: preferred_length, formality, top_topics, activity_window.
    Returns None when insufficient data.
    """
    preferred_length = metrics.get("preferred_length")
    formality = metrics.get("formality")
    top_topics = metrics.get("top_topics", [])

    if preferred_length is None and formality is None and not top_topics:
        return None

    # Formality label
    if formality is not None and formality >= 0.15:
        formality_label = "technical"
    elif formality is not None and formality <= 0.05:
        formality_label = "casual"
    else:
        formality_label = "balanced"

    parts: list[str] = ["[STYLE]"]
    parts.append(f"Recent tone: {formality_label}.")
    if preferred_length is not None:
        parts.append(f"Preferred response length: ~{preferred_length} tokens.")
    if top_topics:
        parts.append(f"Active topics this week: {', '.join(top_topics)}.")

    return " ".join(parts)
