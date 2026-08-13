#!/usr/bin/env python3
"""Repeatable llama-server inference benchmark.

Sends a fixed-size prompt with a fixed generation length to a running
llama-server and records prompt-processing (pp) and text-generation (tg)
tokens/sec from the server's per-request `timings` object.

Usage:
    python scripts/bench_inference.py --label t4-tb4-cmoe-baseline
    python scripts/bench_inference.py --label t8-tb8-cmoe --runs 3 --n-predict 300

Each run prepends a unique nonce paragraph to the prompt so the server-side
prompt cache (per-slot prefix reuse) cannot skew prompt-processing numbers.

Results are appended as CSV to --out (default: runtime-data/bench/inference-bench.csv)
and a median summary is printed at the end.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

# Fixed passage, repeated to build a ~1.5-2k token prompt. Do not edit:
# changing the text invalidates comparisons with previously recorded runs.
PASSAGE = (
    "The Hestia personal assistant coordinates household tasks through a set of "
    "cooperative agents. Each agent maintains a short-term memory of recent "
    "conversations, a long-term store of facts about the household, and a schedule "
    "of pending obligations. When a resident sends a message, the orchestrator "
    "decides which agent should respond, gathers the relevant context, and streams "
    "a reply back over the resident's preferred channel. Reliability matters more "
    "than cleverness: a missed reminder is worse than a plain one.\n"
)

PROMPT_REPEATS = 40  # ~1.6k tokens with the passage above

INSTRUCTION = (
    "\nSummarize the system described above, then write a detailed design "
    "proposal for adding a voice interface, covering audio capture, speech "
    "recognition, turn-taking, and response synthesis. Be thorough and specific."
)


def build_prompt(nonce: str) -> str:
    return f"Run identifier: {nonce}\n\n" + PASSAGE * PROMPT_REPEATS + INSTRUCTION


def run_once(url: str, prompt: str, n_predict: int, timeout: int) -> dict:
    body = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": n_predict,
        "temperature": 0.6,
        "seed": 42,
        "cache_prompt": False,
    }
    req = urllib.request.Request(
        f"{url}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.load(resp)
    wall = time.monotonic() - t0

    usage = data.get("usage", {})
    timings = data.get("timings", {})
    if "prompt_per_second" not in timings:
        raise RuntimeError(f"server response missing timings object: {list(data)}")
    return {
        "prompt_n": usage.get("prompt_tokens"),
        "predicted_n": usage.get("completion_tokens"),
        "pp_tps": round(timings["prompt_per_second"], 2),
        "tg_tps": round(timings["predicted_per_second"], 2),
        "wall_s": round(wall, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8001")
    ap.add_argument("--label", required=True, help="config label recorded with results")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--n-predict", type=int, default=300)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument(
        "--out",
        default="runtime-data/bench/inference-bench.csv",
        type=Path,
    )
    args = ap.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    new_file = not args.out.exists()

    rows = []
    for i in range(args.runs):
        nonce = f"{args.label}-run{i}-{int(time.time())}"
        r = run_once(args.url, build_prompt(nonce), args.n_predict, args.timeout)
        r["label"] = args.label
        r["run"] = i
        r["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        rows.append(r)
        print(
            f"run {i}: pp={r['pp_tps']} t/s ({r['prompt_n']} tok)  "
            f"tg={r['tg_tps']} t/s ({r['predicted_n']} tok)  wall={r['wall_s']}s",
            flush=True,
        )

    with args.out.open("a", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["ts", "label", "run", "prompt_n", "predicted_n", "pp_tps", "tg_tps", "wall_s"],
        )
        if new_file:
            w.writeheader()
        w.writerows(rows)

    pp = statistics.median(r["pp_tps"] for r in rows)
    tg = statistics.median(r["tg_tps"] for r in rows)
    print(f"\n[{args.label}] median over {args.runs} runs: pp={pp} t/s  tg={tg} t/s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
