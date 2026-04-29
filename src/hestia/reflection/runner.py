"""ReflectionRunner — self-improvement via trace analysis."""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from hestia.core.clock import utcnow
from hestia.core.types import Message
from hestia.reflection.store import ProposalStore
from hestia.reflection.types import Proposal

if TYPE_CHECKING:
    from hestia.config import ReflectionConfig
    from hestia.core.inference import InferenceClient
    from hestia.persistence.trace_store import TraceStore

logger = logging.getLogger(__name__)

_PATTERN_PROMPT = (
    "You are a conversation analyst. Review recent traces and extract structured observations.\n"
    "Categories: frustration, correction, slow_turn, repeated_chain, tool_failure.\n"
    'Output JSON: {"observations": [{"category": "...", "turn_id": "...", '
    '"description": "...", "confidence": 0.0-1.0}]}'
)

_PROPOSAL_PROMPT = (
    "You are a self-improvement advisor. Given observations, generate concrete proposals.\n"
    "Types: identity_update, new_chain, tool_fix, policy_tweak.\n"
    'Output JSON: {"proposals": [{"type": "...", "summary": "...", '
    '"evidence": [...], "action": {...}, "confidence": 0.0-1.0}]}'
)


def _extract_json(text: str) -> dict[str, Any]:
    """Extract JSON object from text, tolerating markdown blocks."""
    for pat in (r"```json\s*(.*?)\s*```", r"```\s*(.*?)\s*```"):
        m = re.search(pat, text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {}


class ReflectionRunner:
    """Orchestrates trace analysis → proposal generation → persistence."""

    def __init__(
        self,
        config: ReflectionConfig,
        inference: InferenceClient,
        trace_store: TraceStore,
        proposal_store: ProposalStore,
        on_failure: Any | None = None,
    ) -> None:
        self._config = config
        self._inference = inference
        self._trace_store = trace_store
        self._proposal_store = proposal_store
        self._on_failure = on_failure

    def set_failure_handler(self, handler: Any | None) -> None:
        self._on_failure = handler

    def _record_failure(self, stage: str, exc: Exception) -> None:
        if self._on_failure is not None:
            self._on_failure(stage, exc)

    async def run(self) -> list[Proposal]:
        """Run the full pipeline: mine → generate → persist."""
        if not self._config.enabled:
            return []
        traces = await self._trace_store.list_recent(limit=self._config.lookback_turns)
        if not traces:
            return []
        trace_text = "\n".join(
            f"- turn_id: {t.turn_id}\n  summary: {t.user_input_summary}\n"
            f"  tools: {t.tools_called}\n  outcome: {t.outcome}"
            for t in traces
        )
        try:
            resp = await self._inference.chat(
                messages=[
                    Message(role="system", content=_PATTERN_PROMPT),
                    Message(role="user", content=f"Recent traces:\n{trace_text}"),
                ],
                tools=[],
            )
        except Exception as e:  # noqa: BLE001
            self._record_failure("mining", e)
            logger.exception("Pattern mining failed: %s", e)
            return []
        observations = _extract_json(resp.content or "").get("observations", [])
        if not observations:
            return []
        try:
            resp = await self._inference.chat(
                messages=[
                    Message(role="system", content=_PROPOSAL_PROMPT),
                    Message(
                        role="user",
                        content=json.dumps({"observations": observations}, indent=2),
                    ),
                ],
                tools=[],
            )
        except Exception as e:  # noqa: BLE001
            self._record_failure("proposal", e)
            logger.exception("Proposal generation failed: %s", e)
            return []
        raw = _extract_json(resp.content or "").get("proposals", [])
        items = raw[: self._config.proposals_per_run]
        now, expire = utcnow(), utcnow() + timedelta(days=self._config.expire_days)
        persisted: list[Proposal] = []
        for item in items:
            try:
                proposal = Proposal(
                    id=f"prop_{uuid.uuid4().hex[:16]}",
                    type=item.get("type", "policy_tweak"),
                    summary=item.get("summary", ""),
                    evidence=item.get("evidence", []),
                    action=item.get("action", {}),
                    confidence=float(item.get("confidence", 0.0)),
                    status="pending",
                    created_at=now,
                    expires_at=expire,
                )
                await self._proposal_store.save(proposal)
                persisted.append(proposal)
            except (ValueError, TypeError) as e:
                logger.warning("Skipping malformed proposal: %s", e)
        pruned = await self._proposal_store.prune_expired()
        if pruned:
            logger.info("Pruned %d expired proposals", pruned)
        return persisted
