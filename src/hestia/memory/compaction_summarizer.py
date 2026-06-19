"""Task-aware summarizer used by the /compact meta-command."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from hestia.core.inference import InferenceClient
from hestia.core.types import Message, Session
from hestia.memory.store import MemoryStore

logger = logging.getLogger(__name__)

_COMPACTION_PROMPT = """You are compacting a long-running agent conversation into a durable task-state summary.

Read the conversation below and emit a single JSON object with these exact keys:
- "goal": the current task or goal the user is pursuing.
- "criteria": constraints, preferences, or success criteria the user has stated.
- "progress_done": what has already been accomplished.
- "pending": what still needs to be done.
- "key_findings": important facts, decisions, or results discovered so far.
- "artifact_paths": a list of artifact file paths or handles mentioned
  (e.g. "art_abc123def4", "/path/to/file"). Empty list if none.
- "summary": a concise paragraph synthesizing the task state for the next turn.
  Keep it under {max_chars} characters.

Return ONLY the JSON object. Do not wrap it in markdown, code fences, or explanation.
"""

_INSTRUCTION_PROMPT = """
The user gave this focus instruction for the compaction: "{instruction}".
Bias the summary and preserved fields toward that instruction.
"""


@dataclass
class CompactionSummary:
    """Structured task-state summary produced by compaction."""

    goal: str
    criteria: str
    progress_done: str
    pending: str
    key_findings: str
    artifact_paths: list[str]
    summary: str


@dataclass
class CompactionResult:
    """Result of generating a compaction summary."""

    summary: CompactionSummary
    memory_id: str | None
    token_cost: int


class SessionCompactionSummarizer:
    """Generates a structured, task-aware summary when /compact is invoked."""

    def __init__(
        self,
        inference: InferenceClient,
        memory_store: MemoryStore,
        *,
        max_chars: int = 1500,
        min_messages: int = 4,
    ) -> None:
        self._inference = inference
        self._memory = memory_store
        self._max_chars = max_chars
        self._min_messages = min_messages

    async def summarize_and_store(
        self,
        session: Session,
        history: list[Message],
        instruction: str | None = None,
    ) -> CompactionResult | None:
        """Generate a structured compaction summary and persist task-state memories.

        Returns None when the session is too short to compact or summarization fails.
        """
        if len(history) < self._min_messages:
            return None

        prompt = _COMPACTION_PROMPT.format(max_chars=self._max_chars)
        if instruction:
            prompt += _INSTRUCTION_PROMPT.format(instruction=instruction)

        request_msgs: list[Message] = [
            Message(role="system", content=prompt),
            *(m for m in history if m.role in ("user", "assistant") and m.content),
        ]

        try:
            response = await self._inference.chat(
                messages=request_msgs,
                tools=[],
                slot_id=None,
                reasoning_budget=0,
            )
        except Exception:
            logger.exception("Compaction summarization failed for session %s", session.id)
            return None

        raw_content = (response.content or "").strip()
        if not raw_content:
            logger.warning("Compaction summary produced empty content for %s", session.id)
            return None

        summary = self._parse_summary(raw_content)
        if summary is None:
            logger.warning(
                "Compaction summary for %s was not valid JSON; treating as plain summary",
                session.id,
            )
            # Fall back to a plain synthetic message with the raw model output.
            summary = CompactionSummary(
                goal="",
                criteria="",
                progress_done="",
                pending="",
                key_findings=raw_content,
                artifact_paths=[],
                summary=raw_content[: self._max_chars],
            )

        memory_id = await self._flush_task_state(session, summary)

        return CompactionResult(
            summary=summary,
            memory_id=memory_id,
            token_cost=(response.prompt_tokens or 0) + (response.completion_tokens or 0),
        )

    def _parse_summary(self, raw: str) -> CompactionSummary | None:
        """Parse the model's JSON output into a CompactionSummary."""
        # Strip common markdown wrappers.
        cleaned = raw
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return None

        if not isinstance(data, dict):
            return None

        def _get(key: str) -> str:
            value = data.get(key)
            if value is None or value == "":
                return ""
            if isinstance(value, list):
                return "\n".join(str(item) for item in value)
            return str(value)

        artifact_paths = data.get("artifact_paths") or []
        if not isinstance(artifact_paths, list):
            artifact_paths = []
        artifact_paths = [str(path) for path in artifact_paths if path]

        summary_text = _get("summary") or _get("key_findings")
        if len(summary_text) > self._max_chars:
            summary_text = summary_text[: self._max_chars].rstrip() + "…"

        return CompactionSummary(
            goal=_get("goal"),
            criteria=_get("criteria"),
            progress_done=_get("progress_done"),
            pending=_get("pending"),
            key_findings=_get("key_findings"),
            artifact_paths=artifact_paths,
            summary=summary_text,
        )

    async def _flush_task_state(
        self, session: Session, summary: CompactionSummary
    ) -> str | None:
        """Write structured task-state fields to memory, deduped by exact content.

        Only the narrow task-state fields are flushed. The synthetic summary
        message itself is not stored as a memory here.
        """
        parts: list[str] = []
        if summary.goal:
            parts.append(f"Goal: {summary.goal}")
        if summary.criteria:
            parts.append(f"Criteria: {summary.criteria}")
        if summary.progress_done:
            parts.append(f"Done: {summary.progress_done}")
        if summary.pending:
            parts.append(f"Pending: {summary.pending}")
        if summary.key_findings:
            parts.append(f"Findings: {summary.key_findings}")
        if summary.artifact_paths:
            parts.append(f"Artifacts: {', '.join(summary.artifact_paths)}")

        if not parts:
            return None

        content = "\n".join(parts)

        # Simple exact-match dedup against existing memories for this identity.
        existing = await self._memory.list_memories(
            platform=session.platform,
            platform_user=session.platform_user,
            limit=200,
        )
        for existing_memory in existing:
            if existing_memory.content.strip() == content.strip():
                logger.debug(
                    "Skipping duplicate compaction memory for session %s", session.id
                )
                return existing_memory.id

        memory = await self._memory.save(
            content=content,
            tags=["compaction", "task-state"],
            session_id=session.id,
            platform=session.platform,
            platform_user=session.platform_user,
        )
        return memory.id if memory else None
