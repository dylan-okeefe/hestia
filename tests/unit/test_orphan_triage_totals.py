"""D10: stated tallies over checked-in tables are GENERATED, not typed.

THE TRANSPORTED COUNT (#45 register A9 variant): a header tally drifted
from its table because it was transcribed across an edit.
"""

from __future__ import annotations

import re
from pathlib import Path

TRIAGE = Path(__file__).resolve().parents[2] / "docs" / "audit" / "ORPHAN_TRIAGE.md"


def test_triage_header_totals_match_table() -> None:
    text = TRIAGE.read_text()
    rows = re.findall(r"^\| (?:SEC|BUG|PERF)-\d+ \|[^|]+\| ([^|]+?) \|", text, re.M)
    counts = {
        "FIXED": sum(1 for r in rows if r.strip() == "FIXED"),
        "STILL OPEN": sum(1 for r in rows if r.strip().startswith("STILL OPEN")),
        "NO LONGER APPLIES": sum(1 for r in rows if "NO LONGER" in r),
        "CANNOT DETERMINE": sum(1 for r in rows if "CANNOT" in r),
    }
    m = re.search(
        r"(?P<f>\d+) FIXED ·\s+(?P<s>\d+) STILL OPEN(?:\s*\(incl\.[^)]*\))?"
        r"\s*·\s*(?P<n>\d+) NO LONGER APPLIES ·\s*(?P<c>\d+) CANNOT DETERMINE",
        text,
    )
    assert m, "header no longer carries the expected totals format"
    stated = {
        "FIXED": int(m.group("f")),
        "STILL OPEN": int(m.group("s")),
        "NO LONGER APPLIES": int(m.group("n")),
        "CANNOT DETERMINE": int(m.group("c")),
    }
    assert stated == counts, f"header {stated} != table {counts}"
