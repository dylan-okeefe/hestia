"""Walk relative links in README.md and assert targets exist."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

README_PATH = Path("README.md")
PROJECT_ROOT = Path(".")

# Markdown link pattern: [text](url) or ![alt](url)
LINK_RE = re.compile(r"!?\[([^\]]*)\]\(([^)]+)\)")


def _is_relative(url: str) -> bool:
    """Return True for relative file paths, False for URLs/anchors."""
    if url.startswith(("http://", "https://", "mailto:", "#")):
        return False
    if url.startswith("<") and url.endswith(">"):
        return False
    return True


def _resolve(url: str) -> Path:
    """Resolve a relative URL to a filesystem path."""
    # Strip any anchor fragment
    path_part = url.split("#")[0]
    return (PROJECT_ROOT / path_part).resolve()


def test_readme_relative_links_exist() -> None:
    """Every relative link in README.md must point to an existing file."""
    readme_text = README_PATH.read_text()
    broken: list[str] = []

    for _match in LINK_RE.finditer(readme_text):
        url = _match.group(2)
        if not _is_relative(url):
            continue
        target = _resolve(url)
        if not target.exists():
            broken.append(url)

    if broken:
        pytest.fail(
            f"README.md contains {len(broken)} broken relative link(s):\n"
            + "\n".join(f"  - {u}" for u in broken)
        )
