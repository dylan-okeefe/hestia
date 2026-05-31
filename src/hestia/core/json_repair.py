"""JSON repair utility for malformed tool-call arguments."""

import json
import re


def _extract_fenced_json(text: str) -> str:
    """Extract JSON from markdown code fences."""
    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    return text


def _extract_first_json_object(text: str) -> str | None:
    """Find the first JSON-like object starting with { or [ and return up to its match."""
    start = -1
    for i, ch in enumerate(text):
        if ch in "{[":
            start = i
            break

    if start == -1:
        return None

    open_char = text[start]
    close_char = "}" if open_char == "{" else "]"
    depth = 0
    in_string = False
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            i += 2
            continue
        if ch == '"':
            in_string = not in_string
        elif not in_string:
            if ch == open_char:
                depth += 1
            elif ch == close_char:
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        i += 1

    # Unmatched – return from start to end for balancing later
    return text[start:]


def _escape_string_literals(text: str) -> str:
    """Escape literal newlines/tabs inside quoted strings and normalise quotes to double."""
    result: list[str] = []
    i = 0
    in_string = False
    quote_char = None

    while i < len(text):
        ch = text[i]

        if not in_string:
            if ch in "\"'":
                in_string = True
                quote_char = ch
                result.append('"')
                i += 1
                continue
        else:
            if ch == "\\":
                result.append(ch)
                i += 1
                if i < len(text):
                    result.append(text[i])
                i += 1
                continue
            if ch == quote_char:
                in_string = False
                quote_char = None
                result.append('"')
                i += 1
                continue
            if ch == "\n":
                result.append("\\n")
                i += 1
                continue
            if ch == "\t":
                result.append("\\t")
                i += 1
                continue

        result.append(ch)
        i += 1

    return "".join(result)


def _quote_unquoted_keys(text: str) -> str:
    """Add double quotes around unquoted object keys."""
    result: list[str] = []
    i = 0
    in_string = False

    while i < len(text):
        ch = text[i]

        if ch == "\\" and i + 1 < len(text) and text[i + 1] == '"':
            result.append(ch)
            result.append(text[i + 1])
            i += 2
            continue

        if ch == '"':
            in_string = not in_string
            result.append(ch)
            i += 1
            continue

        if not in_string and (ch.isalpha() or ch == "_"):
            word = ""
            while i < len(text) and (text[i].isalnum() or text[i] == "_"):
                word += text[i]
                i += 1
            rest = text[i:].lstrip()
            if rest.startswith(":"):
                result.append('"')
                result.append(word)
                result.append('"')
            else:
                result.append(word)
            continue

        result.append(ch)
        i += 1

    return "".join(result)


def _fix_trailing_commas(text: str) -> str:
    """Remove trailing commas before } or ]."""
    prev = None
    while text != prev:
        prev = text
        text = re.sub(r",\s*}", "}", text)
        text = re.sub(r",\s*\]", "]", text)
    return text


def _balance_braces(text: str) -> str:
    """Add missing closing braces/brackets, respecting string boundaries."""
    open_braces = 0
    open_brackets = 0
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            i += 2
            continue
        if ch == '"':
            in_string = not in_string
        elif not in_string:
            if ch == "{":
                open_braces += 1
            elif ch == "}":
                open_braces -= 1
            elif ch == "[":
                open_brackets += 1
            elif ch == "]":
                open_brackets -= 1
        i += 1

    text += "}" * max(0, open_braces)
    text += "]" * max(0, open_brackets)
    return text


def repair_json(text: str) -> str | None:
    """Attempt to repair common JSON syntax errors. Return repaired string or None.

    Repair sequence (in order):
    1. Extract from `` ```json `` fences
    2. Extract first ``{...}`` or ``[...]`` object
    3. Replace literal newlines/tabs inside string values with ``\n``/``\t``
    4. Fix trailing commas before ``}`` or ``]``
    5. Replace single quotes with double quotes (simple heuristic)
    6. Add missing closing braces/brackets (balance counting)
    """
    if not text or not text.strip():
        return None

    text = text.strip()

    # 1. Extract from ```json fences
    text = _extract_fenced_json(text)

    # 2. Extract first {...} or [...] object
    extracted = _extract_first_json_object(text)
    if extracted is None:
        return None
    text = extracted

    # 3. Replace literal newlines/tabs inside string values with \n/\t
    # 5. Replace single quotes with double quotes
    text = _escape_string_literals(text)

    # Unquoted keys
    text = _quote_unquoted_keys(text)

    # 4 & 6. Fix trailing commas and balance braces iteratively
    prev = None
    while text != prev:
        prev = text
        text = _fix_trailing_commas(text)
        text = _balance_braces(text)

    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        return None
