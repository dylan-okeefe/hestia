"""Memory maintenance service entry points."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hestia.config import MemoryConfig
from hestia.memory.maintenance.contradictions import (
    ContradictionResolver,
    SupersessionResult,
)
from hestia.memory.maintenance.dedupe import DedupeResult, DeterministicDeduper
from hestia.memory.maintenance.llm_dedupe import LLMDeduper, LLMDedupeResult
from hestia.memory.maintenance.prune import DeterministicPruner, PruneResult
from hestia.memory.store import MemoryStore
from hestia.persistence.maintenance_trace_store import MaintenanceTraceStore

if TYPE_CHECKING:
    from hestia.core.inference import InferenceClient


class MemoryMaintenance:
    """High-level maintenance orchestrator for long-term memory."""

    def __init__(
        self,
        memory_store: MemoryStore,
        inference: InferenceClient | None = None,
        memory_config: MemoryConfig | None = None,
        trace_store: MaintenanceTraceStore | None = None,
    ) -> None:
        self._memory_store = memory_store
        self._inference = inference
        self._memory_config = memory_config or MemoryConfig()
        self._trace_store = trace_store

    async def run_deterministic_dedupe(
        self, platform: str, platform_user: str
    ) -> DedupeResult:
        """Run the deterministic dedupe pass for the given identity."""
        deduper = DeterministicDeduper(
            self._memory_store,
            trace_store=self._trace_store,
            undo_retention_days=self._memory_config.maintenance.undo_retention_days,
        )
        return await deduper.run(platform, platform_user)

    async def run_deterministic_prune(
        self,
        platform: str | None = None,
        platform_user: str | None = None,
    ) -> PruneResult:
        """Run the deterministic prune pass for the given scope."""
        pruner = DeterministicPruner(
            self._memory_store,
            trace_store=self._trace_store,
            undo_retention_days=self._memory_config.maintenance.undo_retention_days,
        )
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
            trace_store=self._trace_store,
            undo_retention_days=self._memory_config.maintenance.undo_retention_days,
        )
        return await deduper.run(platform, platform_user)

    async def run_contradiction_resolution(
        self, platform: str, platform_user: str
    ) -> SupersessionResult:
        """Run the LLM contradiction supersession pass for the given identity.

        Raises:
            RuntimeError: If the service was created without an inference client.
        """
        if self._inference is None:
            raise RuntimeError("Contradiction resolution requires an inference client")

        resolver = ContradictionResolver(
            self._memory_store,
            self._inference,
            max_pairs_per_run=self._memory_config.contradiction_max_pairs_per_run,
            confidence_threshold=self._memory_config.contradiction_confidence_threshold,
            trace_store=self._trace_store,
            undo_retention_days=self._memory_config.maintenance.undo_retention_days,
        )
        return await resolver.run(platform, platform_user)

    async def run_deterministic_pass(
        self, platform: str, platform_user: str
    ) -> tuple[DedupeResult, PruneResult]:
        """Run the nightly deterministic maintenance pass for an identity."""
        dedupe_result = await self.run_deterministic_dedupe(platform, platform_user)
        prune_result = await self.run_deterministic_prune(platform, platform_user)
        return dedupe_result, prune_result

    async def run_llm_pass(
        self, platform: str, platform_user: str
    ) -> tuple[LLMDedupeResult, SupersessionResult]:
        """Run the weekly LLM-assisted maintenance pass for an identity."""
        dedupe_result = await self.run_llm_dedupe(platform, platform_user)
        supersession_result = await self.run_contradiction_resolution(
            platform, platform_user
        )
        return dedupe_result, supersession_result

    # TODO: scope-promotion pass (topic -> global) is deferred to a future loop.
    # It must be review-gated through the Proposals system, with optional
    # ultra-high-confidence identity facts auto-promoting with a digest entry
    # and undo. Do not implement it here; see decisions #9 and spec Loop B.
