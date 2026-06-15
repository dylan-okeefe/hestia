"""Quality monitor: classify degenerate model output and emit tailored corrections."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from hestia.core.types import Message, ToolCall
from hestia.orchestrator.types import Turn


class DegeneratePattern(Enum):
    """Taxonomy of common small-model failure modes."""

    EMPTY_RESPONSE = "empty_response"
    HALLUCINATED_TOOL = "hallucinated_tool"
    REPEATED_IDENTICAL_CALL = "repeated_identical_call"
    PATCH_FAILED = "patch_failed"
    READ_ONLY_STREAK = "read_only_streak"
    GREETING_MID_TASK = "greeting_mid_task"
    TRUNCATED_WRITE_FILE = "truncated_write_file"


@dataclass
class Correction:
    """A specific correction to inject for a degenerate pattern."""

    pattern: DegeneratePattern
    message: str


# Tools that only read state without mutating it.
_READ_ONLY_TOOLS = {
    "read_file",
    "list_dir",
    "browser_get",
    "browser_login",
    "web_search",
    "http_get",
    "current_time",
    "read_artifact",
    "search_memory",
    "list_memories",
    "email_search_and_read",
}

# Meta-tools that inspect tools rather than mutate state. They are excluded
# from read-only streak counting because small models sometimes call them
# while ramping up, and penalizing them the same way as file reads causes
# premature "write your answer" nudges before real work has begun.
_META_INSPECT_TOOLS = {
    "list_tools",
    "describe_tool",
}

# Greeting patterns that indicate a context-loss restart.
_GREETING_PATTERNS = [
    "hello!",
    "hello",
    "hi there!",
    "hi there",
    "hi!",
    "hi",
    "hey!",
    "hey",
    "greetings!",
    "greetings",
    "howdy!",
    "howdy",
    "good morning!",
    "good morning",
    "good afternoon!",
    "good afternoon",
    "good evening!",
    "good evening",
]

# Meta-tools are always available and should not be flagged as hallucinations.
_META_TOOLS = {"list_tools", "describe_tool", "call_tool"}

# Number of patch errors on the same file before we flag PATCH_FAILED.
_PATCH_FAILURE_THRESHOLD = 3

# Number of consecutive read-only tools before we flag READ_ONLY_STREAK.
_READ_ONLY_STREAK_THRESHOLD = 8


async def classify_turn(
    turn: Turn,
    assistant_message: Message,
    history: list[Message],
    allowed_tools: list[str] | None,
    *,
    write_file_handler: Callable[..., Awaitable[str]] | None = None,
    append_to_file_handler: Callable[..., Awaitable[str]] | None = None,
) -> Correction | None:
    """Inspect a single turn and return a tailored correction if it looks degenerate.

    Args:
        turn: The current :class:`Turn` (used for iteration counts).
        assistant_message: The assistant message produced this iteration.
        history: Full conversation history *including* ``assistant_message``.
        allowed_tools: Tools permitted in this session context.
        write_file_handler: Optional handler for recovering truncated write_file calls.
        append_to_file_handler: Optional handler for recovering truncated append_to_file calls.

    Returns:
        A :class:`Correction` if a degenerate pattern was detected, else ``None``.
    """
    if _is_empty_response(assistant_message):
        return Correction(
            pattern=DegeneratePattern.EMPTY_RESPONSE,
            message="Respond with text or a tool call.",
        )

    if _is_hallucinated_tool(assistant_message, allowed_tools):
        valid = ", ".join(sorted(allowed_tools or []))
        return Correction(
            pattern=DegeneratePattern.HALLUCINATED_TOOL,
            message=f"That tool doesn't exist; valid tools are: {valid}",
        )

    repeated_calls = _get_repeated_identical_calls(assistant_message, history)
    if repeated_calls:
        tool_names = [name for name, _ in repeated_calls]
        message = _build_repeated_call_correction(tool_names)
        return Correction(
            pattern=DegeneratePattern.REPEATED_IDENTICAL_CALL,
            message=message,
        )

    patch_file = _patch_failed_file(history)
    if patch_file is not None:
        return Correction(
            pattern=DegeneratePattern.PATCH_FAILED,
            message="Stop patching; read the file and rewrite from scratch.",
        )

    if _is_read_only_streak(history):
        return Correction(
            pattern=DegeneratePattern.READ_ONLY_STREAK,
            message="You have enough context; write your answer.",
        )

    if _is_greeting_mid_task(assistant_message, turn):
        return Correction(
            pattern=DegeneratePattern.GREETING_MID_TASK,
            message="You lost context; continue where you left off, don't restart.",
        )

    truncated_write = _is_truncated_write_file_xml(assistant_message)
    if truncated_write:
        return await _handle_truncated_write_file(
            assistant_message,
            write_file_handler=write_file_handler,
            append_to_file_handler=append_to_file_handler,
        )

    return None


async def _handle_truncated_write_file(
    assistant_message: Message,
    *,
    write_file_handler: Callable[..., Awaitable[str]] | None,
    append_to_file_handler: Callable[..., Awaitable[str]] | None,
) -> Correction:
    """Recover partial content from a truncated write/append call and build a correction."""
    generic = (
        "Your write_file call was too large and got truncated before it could "
        "be executed. Each write_file/append_to_file call MUST have content "
        "shorter than 2000 characters. Write a short header with write_file, "
        "then add sections with append_to_file. Do not put everything in one call."
    )

    recovery = _recover_truncated_write_file(assistant_message.content or "")
    if recovery is None:
        return Correction(
            pattern=DegeneratePattern.TRUNCATED_WRITE_FILE,
            message=generic,
        )

    name, path, partial_content = recovery
    handler: Callable[..., Awaitable[str]] | None = None
    if name == "write_file":
        handler = write_file_handler
    elif name == "append_to_file":
        handler = append_to_file_handler

    if handler is None:
        return Correction(
            pattern=DegeneratePattern.TRUNCATED_WRITE_FILE,
            message=generic,
        )

    try:
        result = await handler(path=path, content=partial_content)
    except Exception:  # noqa: BLE001
        result = None

    if not result or not (result.startswith("Wrote") or result.startswith("Appended")):
        return Correction(
            pattern=DegeneratePattern.TRUNCATED_WRITE_FILE,
            message=generic,
        )

    bytes_written = len(partial_content)
    if name == "append_to_file":
        message = (
            f"Your append_to_file call was truncated before completion. The first "
            f"{bytes_written:,} characters have been appended to {path}. Continue by "
            f"calling append_to_file with the rest of this section. Do not try to "
            f"rewrite the entire file in one call."
        )
    else:
        message = (
            f"Your write_file call was truncated before completion. The first "
            f"{bytes_written:,} characters have been saved to {path}. Continue by "
            f"calling append_to_file with the next section. Do not try to "
            f"rewrite the entire file in one call."
        )

    return Correction(
        pattern=DegeneratePattern.TRUNCATED_WRITE_FILE,
        message=message,
    )


def _recover_truncated_write_file(
    content: str,
) -> tuple[str, str, str] | None:
    """Extract the tool name, path, and partial content from an unclosed XML block.

    The content capture is intentionally lenient: the JSON string is incomplete,
    so we stop at the truncation point and treat whatever we captured as the
    partial content.
    """
    name_match = re.search(r"<function[=:]\s*([^>\s]+)\s*>", content)
    if not name_match:
        return None
    name = name_match.group(1).strip()
    if name not in ("write_file", "append_to_file"):
        return None

    path_match = re.search(r'"path"\s*:\s*"([^"]+)"', content)
    if not path_match:
        return None
    path = path_match.group(1)

    content_match = re.search(r'"content"\s*:\s*"(.*)', content, re.DOTALL)
    if not content_match:
        return None
    partial_content = content_match.group(1)

    return name, path, partial_content


def _is_empty_response(assistant_message: Message) -> bool:
    """True when the assistant emitted neither text, reasoning, nor tool calls."""
    return (
        not assistant_message.content
        and not assistant_message.tool_calls
        and not assistant_message.reasoning_content
    )


def _is_hallucinated_tool(
    assistant_message: Message, allowed_tools: list[str] | None
) -> bool:
    """True when at least one requested tool is not in the allowed set."""
    if allowed_tools is None:
        return False
    allowed = set(allowed_tools) | _META_TOOLS
    return any(tc.name not in allowed for tc in assistant_message.tool_calls or [])


def _is_repeated_identical_call(
    assistant_message: Message, history: list[Message]
) -> bool:
    """True when the current tool calls exactly match the previous turn's."""
    return bool(_get_repeated_identical_calls(assistant_message, history))


def _get_repeated_identical_calls(
    assistant_message: Message, history: list[Message]
) -> list[_ToolCallKey]:
    """Return the repeated tool calls when the current assistant message duplicates
    the previous assistant message's tool calls, else an empty list.
    """
    if not assistant_message.tool_calls:
        return []

    current_calls = _normalise_tool_calls(assistant_message.tool_calls)

    # Find the previous assistant message in history.
    prev = None
    for msg in reversed(history):
        if msg.role == "assistant" and msg is not assistant_message:
            prev = msg
            break

    if prev is None or not prev.tool_calls:
        return []

    prev_calls = _normalise_tool_calls(prev.tool_calls)
    if current_calls == prev_calls:
        return current_calls
    return []


_ToolCallKey = tuple[str, tuple[tuple[str, Any], ...]]


def _build_repeated_call_correction(tool_names: list[str]) -> str:
    """Return a forceful, specific correction for repeated identical tool calls."""
    if len(tool_names) == 1:
        name = tool_names[0]
        if name == "list_tools":
            return (
                "STOP calling list_tools. You already received the complete tool list "
                "in the previous result and in the system prompt. Do not list tools again. "
                "Pick a specific tool from that list and call it, or reply directly to the user."
            )
        return (
            f"STOP calling {name} repeatedly. You already called it with the same arguments; "
            f"calling it again will return the same result. Use a different tool or answer the user."
        )
    names = ", ".join(tool_names)
    return (
        f"STOP repeating the same tool calls ({names}). You already executed them; "
        f"calling them again will return the same result. Use different tools or answer the user."
    )


def _normalise_tool_calls(tool_calls: list[ToolCall]) -> list[_ToolCallKey]:
    """Return a stable, comparable representation of a list of tool calls.

    Argument values may be lists or dicts, so they are recursively frozen into
    hashable tuples before sorting.
    """

    def _freeze(value: Any) -> Any:
        if isinstance(value, dict):
            return tuple(sorted((k, _freeze(v)) for k, v in value.items()))
        if isinstance(value, list):
            return tuple(_freeze(v) for v in value)
        return value

    out: list[_ToolCallKey] = []
    for tc in tool_calls:
        args = tuple(
            sorted((k, _freeze(v)) for k, v in (tc.arguments or {}).items())
        )
        out.append((tc.name, args))
    return out


def _patch_failed_file(history: list[Message]) -> str | None:
    """Return the file path if write_file failed ≥N times on it, else None."""
    # Map tool_call_id -> tool call so we can correlate results.
    tool_call_map: dict[str, ToolCall] = {}
    for msg in history:
        if msg.role == "assistant" and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_call_map[tc.id] = tc

    file_error_counts: dict[str, int] = {}

    for msg in history:
        if msg.role != "tool" or not msg.tool_call_id:
            continue
        matched = tool_call_map.get(msg.tool_call_id)
        if matched is None:
            continue
        if matched.name not in ("edit_file", "write_file"):
            continue
        if not _looks_like_error(msg.content or ""):
            continue
        file_path = _extract_file_path(matched)
        if not file_path:
            continue
        file_error_counts[file_path] = file_error_counts.get(file_path, 0) + 1
        if file_error_counts[file_path] >= _PATCH_FAILURE_THRESHOLD:
            return file_path

    return None


def _looks_like_error(content: str) -> bool:
    """Heuristic to detect error content in a tool result message."""
    lowered = content.lower()
    indicators = [
        "error:",
        "failed",
        "exception",
        "invalid",
        "cannot",
        "can't",
        "could not",
        "permission denied",
        "not found",
        "no such file",
    ]
    return any(ind in lowered for ind in indicators)


def _extract_file_path(tool_call: ToolCall) -> str | None:
    """Extract the target file path from an edit_file or write_call argument dict."""
    args = tool_call.arguments or {}
    return args.get("path") or args.get("file_path") or args.get("filename")


def _is_truncated_write_file_xml(assistant_message: Message) -> bool:
    """True when the assistant emitted an unclosed XML write_file block with huge content.

    The model sometimes ignores the 2000-character chunking rule and emits one
    enormous <tool_call><function=write_file>... block that exceeds max_tokens,
    so the closing tags are never generated and no tool call is executed.
    """
    content = assistant_message.content or ""
    if "<tool_call>" not in content or "</tool_call>" in content:
        return False
    if "<function=write_file>" not in content and "<function=append_to_file>" not in content:
        return False
    # Be conservative: only flag when the content is clearly too long to be one call.
    return len(content) > 1500


def _is_read_only_streak(history: list[Message]) -> bool:
    """True when the last N tool calls are all read-only."""
    count = 0
    for msg in reversed(history):
        if msg.role == "assistant" and msg.tool_calls:
            for tc in reversed(msg.tool_calls):
                if tc.name in _META_INSPECT_TOOLS:
                    # Tool-inspection calls don't count toward read-only streaks.
                    continue
                if tc.name in _READ_ONLY_TOOLS:
                    count += 1
                    if count >= _READ_ONLY_STREAK_THRESHOLD:
                        return True
                else:
                    return False
        elif msg.role == "user" and not msg.correction:
            # Real user messages reset the streak; injected corrections do not,
            # otherwise a correction would hide a continuing read-only loop.
            return False
    return False


def _is_greeting_mid_task(assistant_message: Message, turn: Turn) -> bool:
    """True when the assistant greets the user mid-task."""
    if turn.iterations <= 2:
        return False
    content = (assistant_message.content or "").strip().lower()
    return any(content.startswith(pattern) for pattern in _GREETING_PATTERNS)
