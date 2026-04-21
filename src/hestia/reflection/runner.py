"""ReflectionRunner — three-pass pipeline for self-improvement."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import timedelta
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from hestia.core.clock import utcnow
from hestia.core.types import ChatResponse, Message
from hestia.reflection.prompts import (
    PATTERN_MINING_SYSTEM_PROMPT,
    PROPOSAL_GENERATION_SYSTEM_PROMPT,
)
from hestia.reflection.store import ProposalStore
from hestia.reflection.types import Observation, Proposal

if TYPE_CHECKING:
    from hestia.config import ReflectionConfig
    from hestia.core.inference import InferenceClient
    from hestia.persistence.trace_store import TraceStore

logger = logging.getLogger(__name__)


class ReflectionRunner:
    """Orchestrates the three-pass reflection pipeline.

    Pass 1: Pattern mining — reads traces, extracts observations.
    Pass 2: Proposal generation — turns observations into proposals.
    Pass 3: Queue write — persists proposals to the proposal store.
    """

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

    def set_failure_handler(
        self, handler: Callable[[str, Exception], None] | None
    ) -> None:
        """Attach the scheduler's failure recorder (replaces ad-hoc ``_on_failure`` writes)."""
        self._on_failure = handler

    def _record_failure(self, stage: str, exc: Exception) -> None:
        if self._on_failure is not None:
            self._on_failure(stage, exc)

    async def run(self) -> list[Proposal]:
        """Execute the full three-pass pipeline.

        Returns the list of proposals that were generated and persisted.
        """
        if not self._config.enabled:
            logger.info("Reflection is disabled; skipping run.")
            return []

        logger.info("Starting reflection run (lookback_turns=%d)", self._config.lookback_turns)

        # Pass 1: Pattern mining
        observations = await self._mine_patterns()
        if not observations:
            logger.info("No observations mined; ending reflection run.")
            return []

        # Pass 2: Proposal generation
        proposals = await self._generate_proposals(observations)
        if not proposals:
            logger.info("No proposals generated; ending reflection run.")
            return []

        # Cap proposals per run
        if len(proposals) > self._config.proposals_per_run:
            proposals = proposals[: self._config.proposals_per_run]
            logger.info("Capped proposals to %d", self._config.proposals_per_run)

        # Pass 3: Queue write
        persisted: list[Proposal] = []
        for proposal in proposals:
            await self._proposal_store.save(proposal)
            persisted.append(proposal)
            logger.info("Persisted proposal %s (type=%s, confidence=%.2f)", proposal.id, proposal.type, proposal.confidence)

        # Prune expired proposals as a side effect
        pruned = await self._proposal_store.prune_expired()
        if pruned:
            logger.info("Pruned %d expired proposals", pruned)

        logger.info("Reflection run complete: %d proposals persisted", len(persisted))
        return persisted

    async def _mine_patterns(self) -> list[Observation]:
        """Pass 1: Read recent traces and extract observations via inference."""
        traces = await self._trace_store.list_recent(limit=self._config.lookback_turns)
        if not traces:
            return []

        # Build a structured prompt from traces
        trace_texts = []
        for t in traces:
            trace_texts.append(
                f"- turn_id: {t.turn_id}\n"
                f"  session: {t.session_id}\n"
                f"  summary: {t.user_input_summary}\n"
                f"  tools: {t.tools_called}\n"
                f"  outcome: {t.outcome}\n"
                f"  delegated: {t.delegated}\n"
            )

        user_content = "Recent traces:\n" + "\n".join(trace_texts)

        messages = [
            Message(role="system", content=PATTERN_MINING_SYSTEM_PROMPT),
            Message(role="user", content=user_content),
        ]

        try:
            response = await self._inference.chat(messages=messages, tools=[])
        except Exception as e:  # noqa: BLE001
            self._record_failure("mining", e)
            logger.exception("Pattern mining inference call failed: %s", e)
            return []

        return self._parse_observations(response)

    async def _generate_proposals(self, observations: list[Observation]) -> list[Proposal]:
        """Pass 2: Feed observations to inference and generate structured proposals."""
        obs_list = []
        for obs in observations:
            obs_list.append(
                {
                    "category": obs.category,
                    "turn_id": obs.turn_id,
                    "description": obs.description,
                    "confidence": obs.confidence,
                }
            )

        user_content = json.dumps({"observations": obs_list}, indent=2)

        messages = [
            Message(role="system", content=PROPOSAL_GENERATION_SYSTEM_PROMPT),
            Message(role="user", content=user_content),
        ]

        try:
            response = await self._inference.chat(messages=messages, tools=[])
        except Exception as e:  # noqa: BLE001
            self._record_failure("proposal", e)
            logger.exception("Proposal generation inference call failed: %s", e)
            return []

        return self._parse_proposals(response)

    def _parse_observations(self, response: ChatResponse) -> list[Observation]:
        """Parse the model response into Observation objects."""
        content = response.content or ""
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code block
            data = self._extract_json(content)

        if not isinstance(data, dict):
            logger.warning("Pattern mining response is not a dict: %s", type(data))
            return []

        observations = []
        for item in data.get("observations", []):
            if not isinstance(item, dict):
                continue
            try:
                obs = Observation(
                    category=item.get("category", "tool_failure"),
                    turn_id=item.get("turn_id", ""),
                    description=item.get("description", ""),
                    confidence=float(item.get("confidence", 0.0)),
                )
                observations.append(obs)
            except (ValueError, TypeError) as e:
                logger.warning("Skipping malformed observation: %s", e)

        return observations

    def _parse_proposals(self, response: ChatResponse) -> list[Proposal]:
        """Parse the model response into Proposal objects."""
        content = response.content or ""
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            data = self._extract_json(content)

        if not isinstance(data, dict):
            logger.warning("Proposal generation response is not a dict: %s", type(data))
            return []

        proposals = []
        now = utcnow()
        expire_delta = timedelta(days=self._config.expire_days)

        for item in data.get("proposals", []):
            if not isinstance(item, dict):
                continue
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
                    expires_at=now + expire_delta,
                )
                proposals.append(proposal)
            except (ValueError, TypeError) as e:
                logger.warning("Skipping malformed proposal: %s", e)

        return proposals

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        """Extract JSON object from text, handling markdown code blocks."""
        # Look for ```json ... ``` block
        if "```json" in text:
            start = text.find("```json") + len("```json")
            end = text.find("```", start)
            if end != -1:
                try:
                    result = json.loads(text[start:end].strip())
                    if isinstance(result, dict):
                        return result
                except json.JSONDecodeError:
                    pass

        # Look for ``` ... ``` block
        if "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end != -1:
                try:
                    result = json.loads(text[start:end].strip())
                    if isinstance(result, dict):
                        return result
                except json.JSONDecodeError:
                    pass

        # Look for first { and last }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                result = json.loads(text[start : end + 1])
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass

        return {}
