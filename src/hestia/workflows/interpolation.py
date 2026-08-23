"""Variable interpolation engine for workflow templates."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

VAR_RE = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")

logger = logging.getLogger(__name__)


def interpolate(template: str, context: dict[str, Any]) -> str:
    """Replace {{key}} or {{node_id.field}} placeholders with values from context.

    BUG-069: unresolved placeholders are logged loudly instead of silently
    collapsing to an empty string, and dict/list values are serialized as
    JSON rather than Python repr (which corrupts JSON templates built by
    string concatenation).
    """

    def _replacer(match: re.Match[str]) -> str:
        key = match.group(1)
        parts = key.split(".")
        value: Any = context
        missing = False
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                missing = True
                break
        if missing:
            logger.warning(
                "Interpolation placeholder {{%s}} did not resolve to any "
                "value; substituting empty string",
                key,
            )
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return "" if value is None else str(value)

    return VAR_RE.sub(_replacer, template)
