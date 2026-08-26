"""D9: every directory under tests/ contributes collected items.

A directory that collects nothing is invisible to the whole-tree gate -
the exact shape that let tests/smoke go ungated through L245 (card #45,
register A1 / instance 1).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_every_tests_subdirectory_collects_at_least_one_item() -> None:
    tests_root = REPO / "tests"
    top_dirs = sorted(p for p in tests_root.iterdir() if p.is_dir() and p.name != "__pycache__")
    assert top_dirs, "no test directories found under tests/"

    proc = subprocess.run(
        ["uv", "run", "pytest", "--collect-only", "-q"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    collected_files = {
        line.split("::")[0]
        for line in proc.stdout.splitlines()
        if "::" in line
    }

    problems = []
    for d in top_dirs:
        candidates = list(d.rglob("test_*.py"))
        if not candidates:
            # Fixture/helper directories contain no tests by design.
            continue
        has_file = any(
            f.relative_to(REPO).as_posix() in collected_files for f in candidates
        )
        if not has_file:
            problems.append(f"{d.relative_to(REPO)} owns test files but "
                            "collects none of them")
    assert not problems, (
        "directories contributing zero collected items (invisible to the "
        f"gate): {problems}"
    )


def test_whole_tree_floor_is_recorded() -> None:
    """The suite must stay above a recorded floor so silent mass-deselect
    (a bad marker, an over-eager skip) is visible."""
    floor = 2300
    proc = subprocess.run(
        ["uv", "run", "pytest", "--collect-only", "-q", "-m", "not live"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    m = re.search(r"(\d+)/(\d+)", proc.stdout) or re.search(r"(\d+) tests? collected", proc.stdout)
    total = int(m.group(2) if m.lastindex == 2 and "/" in m.group(0) else m.group(1)) if m else 0
    assert total >= floor, f"only {total} items collected; floor is {floor}"
