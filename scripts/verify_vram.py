#!/usr/bin/env python3
"""Verify that llama.cpp has enough VRAM headroom for the configured slots.

The inference server pre-allocates the KV cache to ``n_ctx_total = n_ctx * np``,
so the GPU memory consumed by the cache is largely fixed at startup.  This script
reads the live slot configuration and current GPU memory usage, then prints a
report.  It returns a non-zero exit code if the projected full-load footprint is
within 10% of the available VRAM.

Usage:
    python scripts/verify_vram.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any, cast
from urllib.request import urlopen

LLAMA_SERVER = "http://127.0.0.1:8001"
VRAM_HEADROOM_FRACTION = 0.10


def _gpu_memory_mb() -> tuple[int, int, int]:
    """Return (used_mb, total_mb, free_mb) from nvidia-smi."""
    output = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=memory.used,memory.total,memory.free",
            "--format=csv,noheader,nounits",
        ],
        text=True,
    )
    used, total, free = (int(x.strip()) for x in output.strip().split(","))
    return used, total, free


def _slot_info() -> list[dict[str, Any]]:
    with urlopen(f"{LLAMA_SERVER}/slots", timeout=10) as resp:
        return cast(list[dict[str, Any]], json.loads(resp.read().decode("utf-8")))


def main() -> int:
    try:
        slots = _slot_info()
    except Exception as exc:
        print(f"ERROR: cannot reach llama-server at {LLAMA_SERVER}: {exc}")
        return 2

    # llama.cpp pre-allocates the full KV cache to n_ctx_total = n_ctx * np at
    # startup.  Therefore the GPU memory reported here (after the model has
    # loaded and slots are idle) already includes the worst-case cache footprint
    # for all three 131,072-token slots.  The projection below just adds a
    # generation working-buffer allowance; it does not assume memory grows
    # linearly as prompts are ingested.
    used_mb, total_mb, free_mb = _gpu_memory_mb()
    n_slots = len(slots)
    per_slot_ctx = slots[0]["n_ctx"] if slots else 0
    total_ctx = n_slots * per_slot_ctx

    generation_allowance_mb = 512
    projected_max_mb = used_mb + generation_allowance_mb
    safe_limit_mb = int(total_mb * (1 - VRAM_HEADROOM_FRACTION))

    print("VRAM verification report")
    print("-" * 40)
    print(f"  GPU total VRAM : {total_mb} MiB")
    print(f"  GPU used VRAM  : {used_mb} MiB")
    print(f"  GPU free VRAM  : {free_mb} MiB")
    print(f"  Slots          : {n_slots}")
    print(f"  n_ctx / slot   : {per_slot_ctx}")
    print(f"  Total n_ctx    : {total_ctx}")
    print(f"  Projected max  : ~{projected_max_mb} MiB (used + {generation_allowance_mb} MiB gen buffer)")
    print(f"  10% headroom   : {safe_limit_mb} MiB")

    if projected_max_mb > safe_limit_mb:
        print("\nFAIL: projected VRAM exceeds safe headroom limit.")
        return 1

    print("\nPASS: VRAM headroom is sufficient for full slots.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
