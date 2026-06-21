"""Memory maintenance service entry points."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hestia.config import MemoryConfig
from hestia.memory.maintenance.dedupe import DedupeResult, DeterministicDeduper
from hestia.memory.maintenance.llm_dedupe import LLMDeduper, LLMDedupeResult
from hestia.memory.maintenance.prune import DeterministicPruner, PruneResult
from hestia.memory.store import MemoryStore

if TYPE_CHECKING:
    from hestia.core.inference import InferenceClient


class MemoryMaintenance:
    """High-level maintenance orchestrator for long-term memory."""

    def __init__(
        self,
        memory_store: MemoryStore,
        inference: InferenceClient | None = None,
        memory_config: MemoryConfig | None = None,
    ) -> None:
        self._memory_store = memory_store
        self._inference = inference
        self._memory_config = memory_config or MemoryConfig()

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

    async def run_llm_dedupe(
        self, platform: str, platform_user: str
    ) -> LLMDedupeResult:
        """Run the LLM near-duplicate merge pass for the given identity.

        Raises:
            RuntimeError: If the service was created without an inference client.
        """
        if self._inference is None:
            raise RuntimeError("LLM dedupe requires an inference client")

        deduper = LLMDeduper(
            self._memory_store,
            self._inference,
            max_pairs_per_run=self._memory_config.llm_dedupe_max_pairs_per_run,
            confidence_threshold=self._memory_config.llm_dedupe_confidence_threshold,
        )
        return await deduper.run(platform, platform_user)
