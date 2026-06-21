"""Memory maintenance service entry points."""

from __future__ import annotations

from hestia.memory.maintenance.dedupe import DedupeResult, DeterministicDeduper
from hestia.memory.maintenance.prune import DeterministicPruner, PruneResult
from hestia.memory.store import MemoryStore


class MemoryMaintenance:
    """High-level maintenance orchestrator for long-term memory."""

    def __init__(self, memory_store: MemoryStore) -> None:
        self._memory_store = memory_store

    async def run_deterministic_dedupe(
        self, platform: str, platform_user: str
    ) -> DedupeResult:
        """Run the deterministic dedupe pass for the given identity."""
        deduper = DeterministicDeduper(self._memory_store)
        return await deduper.run(platform, platform_user)

    async def run_deterministic_prune(
        self,
        platform: str | None = None,
        platform_user: str | None = None,
    ) -> PruneResult:
        """Run the deterministic prune pass for the given scope."""
        pruner = DeterministicPruner(self._memory_store)
        return await pruner.run(platform, platform_user)
