#!/usr/bin/env python3
"""Card-#82 bench harness: card-#68 quick bench + TTFT@32K + greedy quality ref.

Prompts are byte-identical to /tmp/tunebench.py (card #68) so arm numbers
stay comparable. New vs card #68: TTFT after a ~32K prompt (layer-major
prefill metric), measured as time-to-first-streamed-token, median of 2.

Usage:
    python scripts/bench_strata_027.py arm <label>
    python scripts/bench_strata_027.py greedy <outpath>

Arm results append as JSON lines to runtime-data/bench/strata-027-results.jsonl.
Requires `strata monitor` on PATH for the pp/tg numbers (same source as #68).
"""
from __future__ import annotations

import difflib
import json
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

URL = "http://127.0.0.1:8080"
RESULTS = Path(__file__).resolve().parent.parent / "runtime-data/bench/strata-027-results.jsonl"

# --- Card-#68 prompt fixtures (verbatim from /tmp/tunebench.py; do not edit) ---
PASSAGE = ("The Hestia personal assistant coordinates household tasks through cooperative agents. "
"Each agent maintains short-term memory, long-term facts, and a schedule of obligations. "
"When a resident sends a message, the orchestrator decides which agent should respond, "
"gathers the relevant context, and streams a reply. Reliability matters more than "
"cleverness: a missed reminder is worse than a plain one.\n")
INSTR = ("Summarize the system above, then list design considerations for a voice interface.")
GREEDY_PROMPT = ("Run identifier: QUALITY-REF-V1\n\n" + PASSAGE * 10 +
"\nExplain how the orchestrator chooses which agent responds, and why reliability is "
"emphasized over cleverness. Answer in 3-4 paragraphs.")

# ~32k-token prompt for the TTFT arm. Card-#68's *330 repeats landed ~24.5k
# tokens (per its log), so *430 targets ~32k. Actual measured prompt_tokens
# recorded per run as ttft_tok.
TTFT_REPEATS = 430


def chat(prompt: str, max_tokens: int, temp: float = 0.6, timeout: int = 900) -> dict:
    body = {"messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens, "temperature": temp, "seed": 42}
    req = urllib.request.Request(f"{URL}/v1/chat/completions",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def wait_entry(after_ts: float, min_prompt: int = 100, timeout: int = 120) -> dict | None:
    t_end = time.time() + timeout
    while time.time() < t_end:
        out = subprocess.run(["strata", "monitor", "--url", URL, "--once", "--output", "json"],
                             capture_output=True, text=True, timeout=30)
        for e in json.loads(out.stdout)["snapshot"]["recent"]:
            if e["time"] > after_ts and e["prompt_tokens"] >= min_prompt:
                return e
        time.sleep(1)
    return None


def timed(prompt: str, max_tokens: int, temp: float = 0.6) -> dict | None:
    before = time.time()
    data = chat(prompt, max_tokens, temp)
    e = wait_entry(before - 1)
    if not e:
        return None
    return {"pp": round(e["prompt_tokens"] / (e["prompt_ms"] / 1000), 1),
            "tg": round(e["output_tokens"] / (e["decode_ms"] / 1000), 2) if e["decode_ms"] > 0 else 0,
            "prompt_tokens": e["prompt_tokens"], "output_tokens": e["output_tokens"]}


def ttft(prompt: str, timeout: int = 900) -> dict:
    """Time to first streamed content token for one request."""
    body = {"messages": [{"role": "user", "content": prompt}],
            "max_tokens": 8, "temperature": 0.0, "seed": 42, "stream": True}
    req = urllib.request.Request(f"{URL}/v1/chat/completions",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    first_token_s: float | None = None
    usage: dict = {}
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if chunk.get("usage"):
                    usage = chunk["usage"]
                for ch in chunk.get("choices", []):
                    delta = ch.get("delta") or {}
                    token = delta.get("content") or delta.get("reasoning_content")
                    if token and first_token_s is None:
                        first_token_s = time.monotonic() - t0
    except Exception as e:  # noqa: BLE001 — stream boundary; fall back below
        return {"ttft_s": None, "ttft_method": f"stream_failed:{e.__class__.__name__}"}
    if first_token_s is None:
        return {"ttft_s": None, "ttft_method": "stream_no_content"}
    return {"ttft_s": round(first_token_s, 2), "ttft_method": "stream_first_token",
            "prompt_tokens": usage.get("prompt_tokens")}


def med(rows: list, key: str):
    vals = sorted(r[key] for r in rows if r and r.get(key) is not None)
    return statistics.median(vals) if vals else None


def arm(label: str) -> dict:
    short = [timed(f"Run id: {label}-s{i}-{int(time.time())}\n\n" + PASSAGE * 40 + "\n" + INSTR, 256)
             for i in range(2)]
    longp = [timed(f"Run id: {label}-l{i}-{int(time.time())}\n\n" + PASSAGE * 330 +
                   "\nList the key design principles, numbered.", 64) for i in range(2)]
    t_prompt = lambda i: (f"Run id: {label}-t{i}-{int(time.time())}\n\n" + PASSAGE * TTFT_REPEATS +
                          "\nList the key design principles, numbered.")
    tts = [ttft(t_prompt(i)) for i in range(2)]
    r = {"arm": label, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
         "pp_short": med(short, "pp"), "tg": med(short, "tg"),
         "pp_16k": med(longp, "pp"),
         "short_tok": short[0]["prompt_tokens"] if short[0] else None,
         "long_tok": longp[0]["prompt_tokens"] if longp[0] else None,
         "ttft_32k_s": med(tts, "ttft_s"),
         "ttft_method": tts[0].get("ttft_method") if tts else None,
         "ttft_tok": tts[0].get("prompt_tokens") if tts else None}
    print(json.dumps(r), flush=True)
    with RESULTS.open("a") as f:
        f.write(json.dumps(r) + "\n")
    return r


def greedy(outpath: str) -> None:
    data = chat(GREEDY_PROMPT, 400, temp=0)
    text = data["choices"][0]["message"]["content"]
    Path(outpath).write_text(text)
    print(f"quality ref saved: {len(text)} chars -> {outpath}", flush=True)


def diff(ref_path: str, arm_path: str) -> None:
    a = Path(ref_path).read_text().splitlines()
    b = Path(arm_path).read_text().splitlines()
    d = list(difflib.unified_diff(a, b, "reference", "arm", lineterm=""))
    print("\n".join(d) if d else "IDENTICAL")


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "arm":
        arm(sys.argv[2])
    elif mode == "greedy":
        greedy(sys.argv[2])
    elif mode == "diff":
        diff(sys.argv[2], sys.argv[3])
