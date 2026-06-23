"""Prompts and response parsing for the LLM near-duplicate merge pass."""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)


LLM_DEDUPE_SYSTEM_PROMPT = """\
You are a careful memory-deduplication judge for a personal assistant's long-term memory store.

Your task: decide whether two memory entries are duplicates or near-duplicates of the same underlying fact.
They may be exact duplicates, paraphrases, or partial statements that should be combined into one memory.

If they are duplicates or near-duplicates:
- Set `"duplicate": true`
- Set `"confidence"` to a number between 0.0 and 1.0 (only very clear duplicates should be above 0.8)
- Provide `"merged_content"`: a concise, accurate merged version that preserves all distinct
  information and loses no important detail

If they are not duplicates:
- Set `"duplicate": false`
- Set `"confidence"` to a number between 0.0 and 1.0
- Set `"merged_content": null`

Respond with a single JSON object and nothing else:

```json
{
  "duplicate": bool,
  "confidence": float,
  "merged_content": str | null
}
```

Examples:

Memory A: "User prefers dark mode in all apps."
Memory B: "User likes dark mode."
Response: {"duplicate": true, "confidence": 0.95, "merged_content": "User prefers dark mode in all apps."}

Memory A: "Alice's favorite food is pizza."
Memory B: "Alice really enjoys pizza pasta weekends."
Response: {"duplicate": false, "confidence": 0.4, "merged_content": null}

Memory A: "Project Falcon uses Rust and PostgreSQL."
Memory B: "Falcon project backend is written in Rust with a PostgreSQL database."
Response: {"duplicate": true, "confidence": 0.92, "merged_content": "Project Falcon uses Rust and PostgreSQL."}
"""


def _format_memory(memory: object) -> str:
    """Render a memory for the deduplication prompt."""
    # Avoid importing heavy types here; use duck-typed attributes.
    tags = getattr(memory, "tags", [])
    tag_str = ", ".join(tags) if tags else "(none)"
    return (
        f"ID: {getattr(memory, 'id', 'unknown')}\n"
        f"Tags: {tag_str}\n"
        f"Content: {getattr(memory, 'content', '')}"
    )


def build_llm_dedupe_prompt(memory_a: object, memory_b: object) -> str:
    """Build the user prompt for a single candidate pair."""
    return (
        "Judge whether the following two memories are duplicates or "
        "near-duplicates of the same fact.\n\n"
        "Memory A:\n"
        f"{_format_memory(memory_a)}\n\n"
        "Memory B:\n"
        f"{_format_memory(memory_b)}\n\n"
        "Return only the required JSON object."
    )


def parse_llm_dedupe_response(text: str) -> tuple[bool, float, str | None]:
    """Parse the LLM response into (duplicate, confidence, merged_content).

    Tries strict JSON parsing first, then a fallback regex that extracts the
    first JSON object from the response. Any unparseable response is treated
    as a non-duplicate with zero confidence so the memories are left alone.
    """
    text = text.strip()

    # Strip a surrounding markdown code fence if present.
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL).strip()

    def _parse(payload: str) -> tuple[bool, float, str | None] | None:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        duplicate = bool(data.get("duplicate", False))
        confidence = data.get("confidence", 0.0)
        if not isinstance(confidence, (int, float)):
            confidence = 0.0
        merged_content = data.get("merged_content")
        if merged_content is not None and not isinstance(merged_content, str):
            merged_content = str(merged_content)
        return duplicate, float(confidence), merged_content

    result = _parse(text)
    if result is not None:
        return result

    # Fallback: extract the first {...} block.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        result = _parse(match.group(0))
        if result is not None:
            return result

    logger.debug("Could not parse LLM dedupe response as JSON: %r", text[:200])
    return False, 0.0, None


CONTRADICTION_SYSTEM_PROMPT = """\
You are a careful memory-contradiction judge for a personal assistant's long-term memory store.

Your task: decide whether two memory entries contradict each other on the same attribute or fact.
A contradiction only occurs when both memories make incompatible claims about the same single attribute.
Updates, corrections, and changes over time about the same attribute ARE contradictions; the newer fact wins.
Genuinely separate facts about different attributes are NOT contradictions, even if they mention the same person.

If they contradict on the same attribute:
- Set `"contradiction": true`
- Set `"confidence"` to a number between 0.0 and 1.0 (only very clear same-attribute contradictions should be above 0.8)
- Provide `"attribute"`: the short name of the attribute they conflict on (e.g., "location", "preference", "status")
- Provide `"reasoning"`: a concise explanation of why they contradict and which memory is newer

If they do not contradict:
- Set `"contradiction": false`
- Set `"confidence"` to a number between 0.0 and 1.0
- Set `"attribute": null`
- Set `"reasoning": null`

Respond with a single JSON object and nothing else:

```json
{
  "contradiction": bool,
  "confidence": float,
  "attribute": str | null,
  "reasoning": str | null
}
```

Examples:

Memory A: "User lives in NYC."
Memory B: "User lives in LA."
Response: {"contradiction": true, "confidence": 0.95, "attribute": "city", "reasoning": "Newer wins."}

Memory A: "User likes blue."
Memory B: "User likes green."
Response: {"contradiction": true, "confidence": 0.92, "attribute": "color", "reasoning": "Newer wins."}

Memory A: "User owns a home in Austin."
Memory B: "User owns a vacation cabin in Denver."
Response: {"contradiction": false, "confidence": 0.2, "attribute": null, "reasoning": null}

Memory A: "Alice works as an engineer."
Memory B: "Alice is allergic to peanuts."
Response: {"contradiction": false, "confidence": 0.1, "attribute": null, "reasoning": null}
"""


def build_contradiction_prompt(memory_a: object, memory_b: object) -> str:
    """Build the user prompt for a single contradiction candidate pair."""
    return (
        "Judge whether the following two memories contradict each other "
        "on the same attribute or fact.\n\n"
        "Memory A:\n"
        f"{_format_memory(memory_a)}\n\n"
        "Memory B:\n"
        f"{_format_memory(memory_b)}\n\n"
        "Return only the required JSON object."
    )


def parse_contradiction_response(
    text: str,
) -> tuple[bool, float, str | None, str | None]:
    """Parse the LLM response into (contradiction, confidence, attribute, reasoning).

    Tries strict JSON parsing first, then a fallback regex that extracts the
    first JSON object from the response. Any unparseable response is treated
    as a non-contradiction with zero confidence so the memories are left alone.
    """
    text = text.strip()

    # Strip a surrounding markdown code fence if present.
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL).strip()

    def _parse(
        payload: str,
    ) -> tuple[bool, float, str | None, str | None] | None:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        contradiction = bool(data.get("contradiction", False))
        confidence = data.get("confidence", 0.0)
        if not isinstance(confidence, (int, float)):
            confidence = 0.0
        attribute = data.get("attribute")
        if attribute is not None and not isinstance(attribute, str):
            attribute = str(attribute)
        reasoning = data.get("reasoning")
        if reasoning is not None and not isinstance(reasoning, str):
            reasoning = str(reasoning)
        return contradiction, float(confidence), attribute, reasoning

    result = _parse(text)
    if result is not None:
        return result

    # Fallback: extract the first {...} block.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        result = _parse(match.group(0))
        if result is not None:
            return result

    logger.debug("Could not parse contradiction response as JSON: %r", text[:200])
    return False, 0.0, None, None
