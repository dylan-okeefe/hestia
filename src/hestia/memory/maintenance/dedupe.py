"""Deterministic memory deduplication maintenance pass."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from hestia.memory.store import Memory, MemoryStore


@dataclass(frozen=True)
class DedupeResult:
    """Result of a deterministic dedupe pass."""

    merged_count: int
    skipped_protected_count: int


def _normalize_content(text: str) -> str:
    """Normalize text for exact duplicate grouping.

    Lowercase, strip leading/trailing whitespace, and collapse
    consecutive whitespace to a single space.
    """
    lowered = text.lower()
    stripped = lowered.strip()
    return re.sub(r"\s+", " ", stripped)


def _tokenize(text: str) -> set[str]:
    """Tokenize text into a set of lowercase alphanumeric words."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _jaccard(a: str, b: str) -> float:
    """Compute Jaccard similarity over word token sets."""
    tokens_a = _tokenize(a)
    tokens_b = _tokenize(b)
    if not tokens_a and not tokens_b:
        return 1.0
    union = tokens_a | tokens_b
    if not union:
        return 0.0
    intersection = tokens_a & tokens_b
    return len(intersection) / len(union)


def _pick_winner(*memories: Memory) -> Memory:
    """Choose the winner among duplicate memories.

    Preference order:
      1. Newest created_at
      2. Longest content
      3. Lower id (lexicographically)
    """
    return min(
        memories,
        key=lambda m: (
            -m.created_at.timestamp(),
            -len(m.content),
            m.id,
        ),
    )


def _merge_contents(contents: list[str]) -> str:
    """Combine contents, deduplicating lines while preserving order."""
    seen: set[str] = set()
    ordered: list[str] = []
    for content in contents:
        for line in content.splitlines():
            line = line.strip()
            if not line or line in seen:
                continue
            seen.add(line)
            ordered.append(line)
    return "\n\n".join(ordered)


def _merge_tags(*memories: Memory) -> list[str]:
    """Return the ordered union of tags across memories."""
    seen: set[str] = set()
    ordered: list[str] = []
    for memory in memories:
        for tag in memory.tags:
            if tag and tag not in seen:
                seen.add(tag)
                ordered.append(tag)
    return ordered


def _search_excerpt(content: str, max_words: int = 10) -> str:
    """Build a short, sanitized excerpt suitable for FTS search."""
    words = content.split()
    return " ".join(words[:max_words])


class DeterministicDeduper:
    """Exact-normalized and high-overlap FTS duplicate merger."""

    def __init__(self, memory_store: MemoryStore) -> None:
        self._store = memory_store

    async def run(self, platform: str, platform_user: str) -> DedupeResult:
        """Run the deterministic dedupe pass for a single identity.

        Args:
            platform: Platform identifier (e.g. "cli", "matrix").
            platform_user: User identifier on that platform.

        Returns:
            DedupeResult with counts of merged losers and skipped protected memories.
        """
        active = await self._store.list_active_memories(
            platform=platform,
            platform_user=platform_user,
            limit=10_000,
        )

        protected: list[Memory] = []
        unprotected: list[Memory] = []
        for memory in active:
            if self._store.is_protected(memory):
                protected.append(memory)
            else:
                unprotected.append(memory)

        merged_count = 0
        processed_ids: set[str] = set()

        # Phase 1: exact duplicates by normalized content hash.
        groups: dict[str, list[Memory]] = defaultdict(list)
        for memory in unprotected:
            groups[_normalize_content(memory.content)].append(memory)

        for group in groups.values():
            if len(group) <= 1:
                continue
            winner = _pick_winner(*group)
            merged_content = _merge_contents([m.content for m in group])
            merged_tags = _merge_tags(*group)
            await self._store.update(
                winner.id,
                content=merged_content,
                tags=merged_tags,
                platform=platform,
                platform_user=platform_user,
            )
            for memory in group:
                if memory.id == winner.id:
                    continue
                await self._store.soft_delete(
                    memory.id,
                    platform=platform,
                    platform_user=platform_user,
                    reason="deduplicated",
                    superseded_by=winner.id,
                )
                processed_ids.add(memory.id)
                merged_count += 1

        # Phase 2: high-overlap FTS pairs among remaining unmerged memories.
        remaining = [
            m
            for m in unprotected
            if m.id not in processed_ids and not self._store.is_protected(m)
        ]

        for memory in remaining:
            if memory.id in processed_ids:
                continue

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
                if candidate.id == memory.id:
                    continue
                if candidate.id in processed_ids:
                    continue
                if self._store.is_protected(candidate):
                    continue

                if _jaccard(memory.content, candidate.content) <= 0.8:
                    continue

                winner = _pick_winner(memory, candidate)
                loser = candidate if winner.id == candidate.id else memory

                merged_content = _merge_contents([winner.content, loser.content])
                merged_tags = _merge_tags(winner, loser)
                await self._store.update(
                    winner.id,
                    content=merged_content,
                    tags=merged_tags,
                    platform=platform,
                    platform_user=platform_user,
                )
                await self._store.soft_delete(
                    loser.id,
                    platform=platform,
                    platform_user=platform_user,
                    reason="deduplicated",
                    superseded_by=winner.id,
                )
                processed_ids.add(loser.id)
                merged_count += 1
                break

        return DedupeResult(
            merged_count=merged_count,
            skipped_protected_count=len(protected),
        )
