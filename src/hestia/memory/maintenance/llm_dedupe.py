"""LLM-assisted near-duplicate memory merge maintenance pass."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from hestia.core.clock import utcnow
from hestia.core.types import Message
from hestia.memory.maintenance.dedupe import (
    _jaccard,
    _merge_contents,
    _merge_tags,
    _pick_winner,
    _search_excerpt,
)
from hestia.memory.maintenance.prompts import (
    LLM_DEDUPE_SYSTEM_PROMPT,
    build_llm_dedupe_prompt,
    parse_llm_dedupe_response,
)
from hestia.memory.maintenance.scopes import format_scope_key, memory_scope_key
from hestia.memory.maintenance.trace import MaintenanceAction
from hestia.memory.store import Memory, MemoryStore

if TYPE_CHECKING:
    from hestia.core.inference import InferenceClient
    from hestia.persistence.maintenance_trace_store import MaintenanceTraceStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMDedupeResult:
    """Result of an LLM near-duplicate merge pass."""

    merged_count: int
    examined_count: int
    failed_judgements: int = 0
    skipped_sanitized: int = 0


class LLMDeduper:
    """Confidence-gated LLM merge pass for paraphrase/near-duplicate memories."""

    def __init__(
        self,
        memory_store: MemoryStore,
        inference: InferenceClient,
        *,
        max_pairs_per_run: int = 10,
        confidence_threshold: float = 0.8,
        chunk_size: int = 500,
        trace_store: MaintenanceTraceStore | None = None,
        undo_retention_days: int = 7,
    ) -> None:
        self._store = memory_store
        self._inference = inference
        self._max_pairs_per_run = max_pairs_per_run
        self._confidence_threshold = confidence_threshold
        self._chunk_size = chunk_size
        self._trace_store = trace_store
        self._undo_retention_days = undo_retention_days

    async def _record_merge(
        self,
        platform: str,
        platform_user: str,
        winner: Memory,
        loser: Memory,
        confidence: float,
        merged_content: str | None,
        scope: str = "global",
    ) -> None:
        """Record an LLM merge action in the trace store, if configured."""
        if self._trace_store is None:
            logger.info(
                "Maintenance LLM merge: %s superseded by %s (confidence=%.2f)",
                loser.id,
                winner.id,
                confidence,
            )
            return
        now = utcnow()
        action = MaintenanceAction(
            id=f"maint_{uuid.uuid4().hex[:16]}",
            action="merge",
            identity_platform=platform,
            identity_user=platform_user,
            winner_memory_id=winner.id,
            loser_memory_ids=[loser.id],
            reason="llm-deduplicated",
            created_at=now,
            undoable_until=now + timedelta(days=self._undo_retention_days),
            details={
                "confidence": confidence,
                "merged_content": merged_content,
                "scope": scope,
            },
        )
        try:
            await self._trace_store.record(action)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to record LLM dedupe trace")

    async def run(self, platform: str, platform_user: str) -> LLMDedupeResult:
        """Run the LLM near-duplicate merge pass for a single identity.

        Args:
            platform: Platform identifier (e.g. "cli", "matrix").
            platform_user: User identifier on that platform.

        Returns:
            LLMDedupeResult with counts of merged losers and examined pairs.
        """
        active = await self._store.list_active_memories(
            platform=platform,
            platform_user=platform_user,
            limit=self._chunk_size,
        )

        topic_ids_map = await self._store.get_topic_ids_for_memories(
            [memory.id for memory in active]
        )

        unprotected = [
            memory for memory in active if not self._store.is_protected(memory)
        ]

        pairs = await self._generate_candidate_pairs(
            unprotected, platform, platform_user, topic_ids_map
        )

        def _scope_key(memory: Memory) -> tuple[str, ...]:
            return memory_scope_key(
                memory, topic_ids_map.get(memory.id, [])
            )

        merged_count = 0
        examined_count = 0
        failed_judgements = 0
        skipped_sanitized = 0
        processed_ids: set[str] = set()

        for memory_a, memory_b in pairs:
            if memory_a.id in processed_ids or memory_b.id in processed_ids:
                continue

            if _scope_key(memory_a) != _scope_key(memory_b):
                continue

            examined_count += 1
            # BUG-026: one transient inference failure used to abort the whole
            # weekly pass; judge each pair independently and keep going.
            try:
                duplicate, confidence, merged_content = await self._judge_pair(
                    memory_a, memory_b
                )
            except Exception:  # noqa: BLE001 — per-pair containment is the point
                logger.exception(
                    "LLM dedupe judge failed for pair (%s, %s); skipping",
                    memory_a.id,
                    memory_b.id,
                )
                failed_judgements += 1
                continue

            if not duplicate or confidence < self._confidence_threshold:
                continue

            winner = _pick_winner(memory_a, memory_b)
            loser = memory_b if winner.id == memory_a.id else memory_a

            final_content = (
                merged_content
                if merged_content is not None
                else _merge_contents([winner.content, loser.content])
            )
            final_tags = _merge_tags(winner, loser)
            scope_str = format_scope_key(_scope_key(winner))

            # BUG-010: don't soft-delete the loser if the sanitizer rejected
            # the merged content — that would record a successful merge while
            # actually losing information.
            update_ok = await self._store.update(
                winner.id,
                content=final_content,
                tags=final_tags,
                platform=platform,
                platform_user=platform_user,
            )
            if not update_ok:
                logger.warning(
                    "Skipping LLM dedupe merge for winner %s: "
                    "merged content rejected by sanitizer",
                    winner.id,
                )
                skipped_sanitized += 1
                continue
            await self._store.soft_delete(
                loser.id,
                platform=platform,
                platform_user=platform_user,
                reason="llm-deduplicated",
                superseded_by=winner.id,
            )
            await self._record_merge(
                platform,
                platform_user,
                winner,
                loser,
                confidence,
                final_content,
                scope=scope_str,
            )

            processed_ids.add(winner.id)
            processed_ids.add(loser.id)
            merged_count += 1

        return LLMDedupeResult(
            merged_count=merged_count,
            examined_count=examined_count,
            failed_judgements=failed_judgements,
            skipped_sanitized=skipped_sanitized,
        )

    async def _generate_candidate_pairs(
        self,
        memories: list[Memory],
        platform: str,
        platform_user: str,
        topic_ids_map: dict[str, list[str]],
    ) -> list[tuple[Memory, Memory]]:
        """Build candidate pairs from FTS near-misses with Jaccard 0.5–0.8."""
        pairs: list[tuple[Memory, Memory]] = []
        seen_pair_ids: set[frozenset[str]] = set()

        def _scope_key(memory: Memory) -> tuple[str, ...]:
            return memory_scope_key(
                memory, topic_ids_map.get(memory.id, [])
            )

        for memory in memories:
            if len(pairs) >= self._max_pairs_per_run:
                break

            excerpt = _search_excerpt(memory.content)
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
                if _scope_key(candidate) != _scope_key(memory):
                    continue

                pair_key = frozenset({memory.id, candidate.id})
                if pair_key in seen_pair_ids:
                    continue

                similarity = _jaccard(memory.content, candidate.content)
                if 0.5 <= similarity <= 0.8:
                    seen_pair_ids.add(pair_key)
                    pairs.append((memory, candidate))

        return pairs

    async def _judge_pair(
        self, memory_a: Memory, memory_b: Memory
    ) -> tuple[bool, float, str | None]:
        """Ask the LLM whether two memories are duplicates."""
        messages = [
            Message(role="system", content=LLM_DEDUPE_SYSTEM_PROMPT),
            Message(
                role="user",
                content=build_llm_dedupe_prompt(memory_a, memory_b),
            ),
        ]

        response = await self._inference.chat(
            messages,
            temperature=0.1,
            max_tokens=256,
        )

        return parse_llm_dedupe_response(response.content)
