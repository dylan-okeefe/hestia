#!/usr/bin/env python3
"""Card-#96 Step 3.1 helper: TTFT at ~64K tokens (median of 2), stream-first-token.

Reuses bench_strata_027's prompts/ttft so numbers are comparable with its
TTFT@32K (430 repeats -> 31901 tok measured). 860 repeats targets ~64K.
Usage: python scripts/bench_ttft64.py <label>
Appends {"arm": label+"-ttft64", ...} to strata-027-results.jsonl.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_strata_027 import PASSAGE, RESULTS, ttft  # noqa: E402

REPEATS = 860


def main(label: str) -> None:
    rows = []
    for i in range(2):
        prompt = (f"Run id: {label}-t64-{i}-{int(time.time())}\n\n" + PASSAGE * REPEATS +
                  "\nList the key design principles, numbered.")
        rows.append(ttft(prompt))
        print(json.dumps(rows[-1]), flush=True)
    vals = sorted(r["ttft_s"] for r in rows if r.get("ttft_s") is not None)
    r = {"arm": f"{label}-ttft64", "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
         "ttft_64k_s": statistics.median(vals) if vals else None,
         "ttft_method": rows[0].get("ttft_method"), "ttft_tok": rows[0].get("prompt_tokens")}
    print(json.dumps(r), flush=True)
    with RESULTS.open("a") as f:
        f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main(sys.argv[1])
