"""Classify tool-result content into high-level failure categories."""

import re
from enum import Enum, auto


class ToolResultCategory(Enum):
    """High-level outcome of a tool call."""

    SUCCESS = auto()
    TIMEOUT = auto()
    BLOCKED = auto()
    NOT_FOUND = auto()
    TRANSIENT_OTHER = auto()


def classify_tool_result(content: str, tool_name: str = "") -> ToolResultCategory:
    """Classify a tool-result string.

    The preferred signal is an explicit ``[CATEGORY: <name>]`` marker emitted by
    the tool.  If no marker is present, the content is treated as ``SUCCESS``;
    this avoids misfiring on legitimate output that happens to contain words like
    "error", "404", or "login".  Tools that want a non-success classification
    must embed the marker.
    """
    lowered = (content or "").lower()

    marker_match = re.search(r"\[category:\s*([a-z_]+)\]", lowered)
    if marker_match:
        name = marker_match.group(1).upper()
        try:
            return ToolResultCategory[name]
        except KeyError:
            pass

    return ToolResultCategory.SUCCESS
