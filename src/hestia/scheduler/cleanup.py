"""Lightweight cleanup routines for scheduler and database maintenance."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from hestia.persistence.error_resolution_store import ErrorResolutionStore

logger = logging.getLogger(__name__)


async def run_error_resolution_cleanup(
    store: ErrorResolutionStore,
    *,
    interval_days: int = 7,
    retention_days: int = 30,
) -> None:
    """Background loop that cleans up old error resolution entries.

    Runs indefinitely with the specified interval between cleanups.
    """
    while True:
        await asyncio.sleep(timedelta(days=interval_days).total_seconds())
        try:
            deleted = await store.clear_old(days=retention_days)
            logger.info("Cleaned up %d old error resolutions", deleted)
        except Exception:
            logger.exception("Error resolution cleanup failed")


async def run_maintenance_trace_cleanup(
    store: Any,
    *,
    interval_hours: int = 24,
    retention_days: int = 14,
) -> None:
    """Background loop that prunes memory-maintenance traces past their undo
    horizon. Traces embed merged-content blobs and previously grew unbounded
    (BUG-075). Runs indefinitely.
    """
    while True:
        await asyncio.sleep(timedelta(hours=interval_hours).total_seconds())
        try:
            deleted = await store.clear_old(days=retention_days)
            if deleted:
                logger.info("Pruned %d expired maintenance traces", deleted)
        except Exception:
            logger.exception("Maintenance trace cleanup failed")
