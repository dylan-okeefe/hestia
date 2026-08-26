"""D6: every finding-ID citation in src/ is pinned by a test or waived.

Waivers live in docs/audit/FINDING_PIN_WAIVERS.md as `ID | reason | evidence`.
A waiver with an empty reason/evidence or a bare "n/a" fails this detector -
a rubber-stamp waiver file is the same defect as the comments it replaces.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
TESTS = REPO / "tests"
WAIVERS = REPO / "docs" / "audit" / "FINDING_PIN_WAIVERS.md"
ID_RE = re.compile(r"\b(?:BUG|SEC|PERF)-\d+\b")
LINE_RE = re.compile(r"^([A-Z]+-\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*$")


def _ids_in(path: Path) -> set[str]:
    return set(ID_RE.findall(path.read_text(encoding="utf-8", errors="replace")))


def test_every_src_citation_is_pinned_or_waived() -> None:
    src_ids: set[str] = set()
    for path in SRC.rglob("*.py"):
        src_ids |= _ids_in(path)
    test_ids: set[str] = set()
    for path in TESTS.rglob("*.py"):
        test_ids |= _ids_in(path)

    waived: dict[str, tuple[str, str]] = {}
    for raw in WAIVERS.read_text().splitlines():
        m = LINE_RE.match(raw.strip())
        if not m:
            continue
        fid, reason, evidence = m.groups()
        assert len(reason) > 3 and reason.strip().lower() != "n/a", (
            f"waiver for {fid} has no real reason: {raw!r}"
        )
        assert len(evidence) > 3 and evidence.strip().lower() != "n/a", (
            f"waiver for {fid} has no alternative evidence: {raw!r}"
        )
        waived[fid] = (reason, evidence)

    unpinned = sorted(src_ids - test_ids - set(waived))
    assert not unpinned, (
        f"{len(unpinned)} finding IDs cited in src have no pinning test and "
        f"no waiver: {unpinned}. Write the test, or add a reasoned waiver "
        f"line to {WAIVERS.relative_to(REPO)}."
    )
    # Waived rows must still correspond to something real.
    stray = sorted(set(waived) - src_ids)
    assert not stray, f"waiver rows cite IDs absent from src/: {stray}"
