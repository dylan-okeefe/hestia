"""Variable interpolation engine for workflow templates."""

from __future__ import annotations

import re
from typing import Any

VAR_RE = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def interpolate(template: str, context: dict[str, Any]) -> str:
    """Replace {{key}} or {{node_id.field}} placeholders with values from context."""

    def _replacer(match: re.Match[str]) -> str:
        key = match.group(1)
        parts = key.split(".")
        value = context
        for part in parts:
            value = value.get(part, "") if isinstance(value, dict) else ""
        return str(value) if value is not None else ""

    return VAR_RE.sub(_replacer, template)
