"""Shared background tick loop (L248/#58 round 3).

One implementation of "sleep, tick, log failures, repeat" so every
scheduler runs its cadence from a single site. Schedulers expose
``tick_loop`` built on :func:`run_tick_loop`; serve and the standalone
daemon both create tasks from those methods instead of hand-rolling loops.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)


async def run_tick_loop(
    tick: Callable[..., Awaitable[Any]],
    *,
    interval_seconds: float = 60.0,
    name: str,
) -> None:
    """Run *tick* every *interval_seconds* until cancelled.

    A failing tick is logged and does not end the loop (BUG-013 lesson:
    one bad pass must not kill the process).
    """
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await tick()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — the loop survives any tick failure
            logger.exception("%s tick failed", name)
