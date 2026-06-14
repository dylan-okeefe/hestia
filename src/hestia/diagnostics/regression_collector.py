"""Collect real failing payloads as regression fixtures.

Set ``HESTIA_REGRESSION_FIXTURES_DIR`` to a directory and the orchestrator will
write anonymized snapshots of malformed tool calls, degenerate turns, and
transient tool failures there. These are far better regression fixtures than
invented examples because they capture the exact output of the deployed model.
"""

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hestia.diagnostics.scrub import scrub_text


_ENV_VAR = "HESTIA_REGRESSION_FIXTURES_DIR"
_AUTO_SCRUB_ENV_VAR = "HESTIA_REGRESSION_AUTO_SCRUB"


def _scrub_payload(value: Any) -> Any:
    """Recursively scrub strings inside a payload dict/list."""
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        return {k: _scrub_payload(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_payload(v) for v in value]
    return value


def _safe_name(name: str) -> str:
    """Sanitize a string for use in a filename."""
    return re.sub(r"[^\w\-]+", "_", name).strip("_")[:80]


def _output_dir(category: str) -> Path | None:
    """Return the target directory for a fixture category, or None if disabled."""
    raw = os.environ.get(_ENV_VAR)
    if not raw:
        return None
    path = Path(raw).expanduser().resolve() / _safe_name(category)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write(category: str, name: str, payload: dict[str, Any]) -> Path | None:
    """Write a timestamped fixture file and return its path."""
    out = _output_dir(category)
    if out is None:
        return None
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    filename = f"{_safe_name(name)}_{timestamp}.json"
    if os.environ.get(_AUTO_SCRUB_ENV_VAR):
        payload = _scrub_payload(payload)
    fixture = {
        "captured_at": datetime.now(UTC).isoformat(),
        "category": category,
        **payload,
    }
    path = out / filename
    path.write_text(json.dumps(fixture, indent=2, default=str), encoding="utf-8")
    return path


def maybe_collect_malformed_tool_call(
    tool_name: str,
    raw_arguments: Any,
    source: str = "",
) -> Path | None:
    """Capture a tool call whose arguments could not be parsed as a dict."""
    return _write(
        "malformed_tool_calls",
        tool_name,
        {
            "tool_name": tool_name,
            "raw_arguments": raw_arguments,
            "raw_arguments_type": type(raw_arguments).__name__,
            "source": source,
        },
    )


def maybe_collect_degenerate_turn(
    correction_name: str,
    history: list[Any],
) -> Path | None:
    """Capture the transcript leading to a degenerate-pattern correction."""
    # Keep only assistant/user/tool messages with minimal fields to avoid
    # leaking sensitive content while preserving the shape of the failure.
    slim_history = []
    for msg in history:
        slim = {
            "role": getattr(msg, "role", None),
            "content": getattr(msg, "content", None),
            "tool_calls": [
                {"name": tc.name, "arguments": tc.arguments}
                for tc in (getattr(msg, "tool_calls", None) or [])
            ],
            "tool_call_id": getattr(msg, "tool_call_id", None),
        }
        slim_history.append(slim)
    return _write(
        "degenerate_turns",
        correction_name,
        {
            "correction": correction_name,
            "history": slim_history,
        },
    )


def maybe_collect_tool_failure(
    tool_name: str,
    arguments: dict[str, Any],
    result: str,
) -> Path | None:
    """Capture a transient tool failure worth retrying later."""
    return _write(
        "tool_failures",
        tool_name,
        {
            "tool_name": tool_name,
            "arguments": arguments,
            "result": result,
        },
    )
