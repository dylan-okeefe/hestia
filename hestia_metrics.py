#!/usr/bin/env python3
"""
hestia_metrics.py — write a metrics.json the resume generator can query.

Goes in the ROOT of the Hestia repo. Run it as part of your dev loop (a pre-commit
hook, a make target, or a step Kimi runs after a batch) so the committed numbers
stay current. The resume on dylanokeefe.dev fetches this file's raw GitHub URL, so
once it's committed the resume updates itself — no hand-editing the counts.

    python hestia_metrics.py            # writes ./metrics.json, prints a summary
    python hestia_metrics.py --check    # print what it found, don't write

The COUNT LOGIC below is a starting point keyed to common layouts. Adjust the
CONFIG globs to match Hestia's actual structure; the script prints what it found
so you can sanity-check before trusting it.
"""
import argparse
import contextlib
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# ---- CONFIG: adjust these to match the repo -------------------------------
PY_EXCLUDE = {".git", ".venv", "venv", "node_modules", "dist", "build", "__pycache__", ".mypy_cache"}
ADR_DIRS   = ["docs/adr", "docs/adrs", "docs/decisions", "adr", "doc/adr"]   # first match wins
LOOPS_DIRS = ["docs/development-process/loops", "loops", "docs/loops", ".loops"]  # loop docs live here
LOOPS_GLOB = "docs/development-process/**/L[0-9]*.md"  # used to detect strays outside LOOPS_DIRS
LOOPS_COUNTER = ".loop_count"   # OR a plain-text file holding a single integer (takes priority if present)
# ---------------------------------------------------------------------------


def python_loc() -> int:
    total = 0
    for p in ROOT.rglob("*.py"):
        if any(part in PY_EXCLUDE for part in p.parts):
            continue
        with contextlib.suppress(Exception):
            total += sum(1 for line in p.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip())
    return total


def tests() -> tuple[int, int]:
    files: set[Path] = set()
    count = 0
    pat = re.compile(r"^\s*(?:async\s+)?def\s+test_", re.M)
    for p in ROOT.rglob("*.py"):
        if any(part in PY_EXCLUDE for part in p.parts):
            continue
        if p.name.startswith("test_") or p.name.endswith("_test.py") or "tests" in p.parts:
            hits = 0
            with contextlib.suppress(Exception):
                hits = len(pat.findall(p.read_text(encoding="utf-8", errors="ignore")))
            if hits:
                files.add(p)
                count += hits
    return count, len(files)


def adrs() -> int:
    for d in ADR_DIRS:
        path = ROOT / d
        if path.is_dir():
            return sum(
                1 for f in path.glob("*.md")
                if f.stem.lower() not in {"readme", "index", "template", "0000-template"}
            )
    return 0


def loops() -> int:
    counter = ROOT / LOOPS_COUNTER
    if counter.exists():
        with contextlib.suppress(Exception):
            return int(counter.read_text().strip())
    for d in LOOPS_DIRS:
        path = ROOT / d
        if path.is_dir():
            return sum(
                1 for f in path.glob("*.md")
                if f.stem.lower() not in {"readme", "index", "template"}
            )
    return 0


def stray_loops() -> list[Path]:
    """Return loop-spec files found outside the canonical loops directory."""
    canonical = ROOT / LOOPS_DIRS[0]
    return [
        p for p in ROOT.glob(LOOPS_GLOB)
        if "reviews" not in p.parts
        and not p.resolve().is_relative_to(canonical.resolve())
    ]


def collect() -> dict[str, object]:
    t, tf = tests()
    return {
        "python_loc": python_loc(),
        "tests": t,
        "test_files": tf,
        "adrs": adrs(),
        "loops": loops(),
        "updated": date.today().isoformat(),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Write metrics.json for the resume to query.")
    ap.add_argument("--check", action="store_true", help="Print what was found without writing")
    args = ap.parse_args()

    m = collect()
    width = max(len(k) for k in m)
    print("Hestia metrics:")
    for k, v in m.items():
        print(f"  {k.ljust(width)} : {v}")

    strays = stray_loops()
    if strays:
        print("\nWarning: loop files found outside the canonical loops directory:")
        for p in sorted(strays):
            print(f"  - {p.relative_to(ROOT)}")
        print(f"\nMove them into {LOOPS_DIRS[0]}/ so the loop count stays accurate.")

    if not args.check:
        (ROOT / "metrics.json").write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8")
        print("\nWrote metrics.json — commit it so the resume picks it up.")


if __name__ == "__main__":
    main()
