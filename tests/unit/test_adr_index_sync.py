"""D2: docs/DECISIONS.md indexes every ADR file, and every index link
resolves. Drift here hides decisions (ADR-052/053 shipped unindexed)."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADR_DIR = REPO / "docs" / "adr"
INDEX = REPO / "docs" / "DECISIONS.md"


def test_every_adr_file_is_indexed() -> None:
    files = {p.name for p in ADR_DIR.glob("ADR-*.md")}
    index = INDEX.read_text()
    missing = sorted(name for name in files if name not in index)
    assert not missing, f"ADR files missing from docs/DECISIONS.md: {missing}"


def test_index_links_resolve_to_files() -> None:
    index = INDEX.read_text()
    linked = set(re.findall(r"\(adr/(ADR-[^\)]+)\)", index))
    broken = sorted(link for link in linked if not (ADR_DIR / link).exists())
    assert not broken, f"DECISIONS.md links to nonexistent ADR files: {broken}"
