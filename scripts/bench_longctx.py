#!/usr/bin/env python3
"""Card-#96 Step 3.7 helpers: TTFT at ~128K/~256K tokens and a long-needle recall probe.

Reuses bench_strata_027's fixtures. ~74.19 tokens per PASSAGE repeat
(31900 tok / 430 repeats measured). Usage:
    python scripts/bench_longctx.py ttft <label> <repeats>
    python scripts/bench_longctx.py needle <label> <bury_repeats> <tail_repeats>
Appends results to runtime-data/bench/strata-027-results.jsonl.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_strata_027 import PASSAGE, RESULTS, chat, ttft  # noqa: E402

FACT = "The retrieval codeword for this session is PURPLE-FALCON-7741."
QUESTION = "What is the retrieval codeword for this session? Answer with the codeword only."


def cmd_ttft(label: str, repeats: int) -> None:
    rows = []
    for i in range(2):
        prompt = (f"Run id: {label}-ttft{repeats}-{i}-{int(time.time())}\n\n" + PASSAGE * repeats +
                  "\nList the key design principles, numbered.")
        rows.append(ttft(prompt))
        print(json.dumps(rows[-1]), flush=True)
    vals = sorted(r["ttft_s"] for r in rows if r.get("ttft_s") is not None)
    r = {"arm": f"{label}-ttft{repeats}", "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
         "ttft_s": statistics.median(vals) if vals else None,
         "ttft_method": rows[0].get("ttft_method"), "ttft_tok": rows[0].get("prompt_tokens")}
    print(json.dumps(r), flush=True)
    with RESULTS.open("a") as f:
        f.write(json.dumps(r) + "\n")


def cmd_needle(label: str, bury: int, tail: int) -> None:
    prompt = (f"Run id: {label}-needle-{int(time.time())}\n\n" + PASSAGE * bury +
              "\n" + FACT + "\n" + PASSAGE * tail + "\n" + QUESTION)
    r = chat(prompt, 512, temp=0.0, timeout=3600)
    msg = r["choices"][0]["message"]
    text = (msg.get("content") or "") + " " + (msg.get("reasoning_content") or "")
    text = text.strip()
    ok = "PURPLE-FALCON-7741" in text.upper().replace(" ", "")
    out = {"arm": f"{label}-needle", "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "prompt_tokens": r["usage"]["prompt_tokens"], "recall": ok, "answer": text[:120]}
    print(json.dumps(out), flush=True)
    with RESULTS.open("a") as f:
        f.write(json.dumps(out) + "\n")


def cmd_decode(label: str, repeats: int, max_tokens: int) -> None:
    from bench_strata_027 import timed
    prompt = (f"Run id: {label}-dec{repeats}-{int(time.time())}\n\n" + PASSAGE * repeats +
              "\nSummarize the above briefly.")
    rows = [timed(prompt, max_tokens) for _ in range(2)]
    for r in rows:
        print(json.dumps(r), flush=True)
    out = {"arm": f"{label}-decode{repeats}", "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "pp": rows[0].get("pp"), "tg": rows[0].get("tg"),
           "tg_med": statistics.median([r["tg"] for r in rows if r.get("tg")]),
           "prompt_tokens": rows[0].get("prompt_tokens")}
    print(json.dumps(out), flush=True)
    with RESULTS.open("a") as f:
        f.write(json.dumps(out) + "\n")


if __name__ == "__main__":
    if sys.argv[1] == "ttft":
        cmd_ttft(sys.argv[2], int(sys.argv[3]))
    elif sys.argv[1] == "needle":
        cmd_needle(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
    else:
        cmd_decode(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
