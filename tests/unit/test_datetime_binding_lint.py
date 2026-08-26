"""D11: a comparison bound against a DateTime column must use the same
format the column's writer uses.

BUG-067 family: isoformat strings compared against datetime-object-written
rows silently mismatch same-day values. This heuristic lint covers the
known hot columns; new DateTime comparisons should extend WRITES_AS_OBJECT.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "hestia"

# Columns proven (by their writers) to bind datetime OBJECTS through
# SQLAlchemy. An .isoformat() comparison against one of these is the bug.
WRITES_AS_OBJECT = {
    "last_active_at",
}

ISO_BINDING_RE = re.compile(r"\.isoformat\(\)")


def test_datetime_object_columns_are_not_compared_to_isoformat_strings() -> None:
    problems: list[str] = []
    for path in SRC.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        lines = path.read_text(errors="replace").splitlines()
        # Find isoformat-derived cutoff/param assignments, then look for a
        # comparison against a watched column within the next 15 lines.
        for i, line in enumerate(lines):
            if ".isoformat()" not in line:
                continue
            window = "\n".join(lines[i : i + 15])
            for col in WRITES_AS_OBJECT:
                if re.search(rf"{col}\s*(?:>=|<=|<|>|=)\s*:\w+", window):
                    rel = path.relative_to(SRC.parent.parent)
                    problems.append(f"{rel}:{i + 1} compares {col} against an isoformat string")
    assert not problems, (
        "DateTime-object columns compared against isoformat strings "
        f"(BUG-067 class): {problems}"
    )
