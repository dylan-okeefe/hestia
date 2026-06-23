"""LLM-assisted contradiction detection and supersession maintenance pass."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from hestia.core.clock import utcnow
from hestia.core.types import Message
from hestia.memory.maintenance.dedupe import _pick_winner, _search_excerpt
from hestia.memory.maintenance.prompts import (
    CONTRADICTION_SYSTEM_PROMPT,
    build_contradiction_prompt,
    parse_contradiction_response,
)
from hestia.memory.maintenance.trace import MaintenanceAction
from hestia.memory.store import Memory, MemoryStore

if TYPE_CHECKING:
    from hestia.core.inference import InferenceClient
    from hestia.persistence.maintenance_trace_store import MaintenanceTraceStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SupersessionResult:
    """Result of a contradiction resolution pass."""

    superseded_count: int
    examined_count: int


class ContradictionResolver:
    """Confidence-gated LLM contradiction detection pass.

    When two active memories conflict on the same attribute, the newer fact
    supersedes the older. Protected memories (pinned, user-authored, or
    recently recalled) are never candidates for supersession.
    """

    def __init__(
        self,
        memory_store: MemoryStore,
        inference: InferenceClient,
        *,
        confidence_threshold: float = 0.8,
        max_pairs_per_run: int = 10,
        chunk_size: int = 500,
        trace_store: MaintenanceTraceStore | None = None,
        undo_retention_days: int = 7,
    ) -> None:
        self._store = memory_store
        self._inference = inference
        self._confidence_threshold = confidence_threshold
        self._max_pairs_per_run = max_pairs_per_run
        self._chunk_size = chunk_size
        self._trace_store = trace_store
        self._undo_retention_days = undo_retention_days

    async def _record_supersede(
        self,
        platform: str,
        platform_user: str,
        winner: Memory,
        loser: Memory,
        attribute: str | None,
        reasoning: str | None,
        confidence: float,
    ) -> None:
        """Record a supersession action in the trace store, if configured."""
        if self._trace_store is None:
            logger.info(
                "Maintenance supersede: %s superseded by %s on attribute=%s",
                loser.id,
                winner.id,
                attribute,
            )
            return
        now = utcnow()
        action = MaintenanceAction(
            id=f"maint_{uuid.uuid4().hex[:16]}",
            action="supersede",
            identity_platform=platform,
            identity_user=platform_user,
            winner_memory_id=winner.id,
            loser_memory_ids=[loser.id],
            reason="superseded",
            created_at=now,
            undoable_until=now + timedelta(days=self._undo_retention_days),
            details={
                "attribute": attribute,
                "reasoning": reasoning,
                "confidence": confidence,
            },
        )
        try:
            await self._trace_store.record(action)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to record contradiction supersession trace")

    async def run(self, platform: str, platform_user: str) -> SupersessionResult:
        """Run the contradiction resolution pass for a single identity.

        Args:
            platform: Platform identifier (e.g. "cli", "matrix").
            platform_user: User identifier on that platform.

        Returns:
            SupersessionResult with counts of superseded losers and examined pairs.
        """
        active = await self._store.list_active_memories(
            platform=platform,
            platform_user=platform_user,
            limit=self._chunk_size,
        )

        unprotected = [
            memory for memory in active if not self._store.is_protected(memory)
        ]

        pairs = await self._generate_candidate_pairs(
            unprotected, platform, platform_user
        )

        superseded_count = 0
        examined_count = 0
        processed_ids: set[str] = set()

        for memory_a, memory_b in pairs:
            if memory_a.id in processed_ids or memory_b.id in processed_ids:
                continue

            examined_count += 1
            contradiction, confidence, attribute, reasoning = await self._judge_pair(
                memory_a, memory_b
            )

            if not contradiction or confidence < self._confidence_threshold:
                continue

            winner = _pick_winner(memory_a, memory_b)
            loser = memory_b if winner.id == memory_a.id else memory_a

            note = (
                f"\n\n[Superseded by {winner.id}"
                f" on attribute '{attribute or 'unknown'}': "
                f"{reasoning or 'no reasoning provided'}]"
            )
            await self._store.update(
                loser.id,
                content=loser.content + note,
                platform=platform,
                platform_user=platform_user,
            )
            await self._store.soft_delete(
                loser.id,
                platform=platform,
                platform_user=platform_user,
                reason="superseded",
                superseded_by=winner.id,
            )
            await self._record_supersede(
                platform,
                platform_user,
                winner,
                loser,
                attribute,
                reasoning,
                confidence,
            )

            processed_ids.add(winner.id)
            processed_ids.add(loser.id)
            superseded_count += 1

        return SupersessionResult(
            superseded_count=superseded_count,
            examined_count=examined_count,
        )

    async def _generate_candidate_pairs(
        self,
        memories: list[Memory],
        platform: str,
        platform_user: str,
    ) -> list[tuple[Memory, Memory]]:
        """Build candidate pairs from FTS near-misses among unprotected memories."""
        pairs: list[tuple[Memory, Memory]] = []
        seen_pair_ids: set[frozenset[str]] = set()

        for memory in memories:
            if len(pairs) >= self._max_pairs_per_run:
                break

            excerpt = _search_excerpt(memory.content, max_words=3)
            if not excerpt:
                continue

            candidates = await self._store.search(
                excerpt,
                limit=10,
                platform=platform,
                platform_user=platform_user,
            )

            for candidate in candidates:
                if len(pairs) >= self._max_pairs_per_run:
                    break
                if candidate.id == memory.id:
                    continue
                if self._store.is_protected(candidate):
                    continue

                pair_key = frozenset({memory.id, candidate.id})
                if pair_key in seen_pair_ids:
                    continue

                seen_pair_ids.add(pair_key)
                pairs.append((memory, candidate))

        return pairs

    async def _judge_pair(
        self, memory_a: Memory, memory_b: Memory
    ) -> tuple[bool, float, str | None, str | None]:
        """Ask the LLM whether two memories contradict on the same attribute."""
        messages = [
            Message(role="system", content=CONTRADICTION_SYSTEM_PROMPT),
            Message(
                role="user",
                content=build_contradiction_prompt(memory_a, memory_b),
            ),
        ]

        response = await self._inference.chat(
            messages,
            temperature=0.1,
            max_tokens=256,
        )

        return parse_contradiction_response(response.content)
