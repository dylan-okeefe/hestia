"""Tests that README.md stays accurate vs. the codebase."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

README_PATH = Path("README.md")
BUILTIN_TOOLS_DIR = Path("src/hestia/tools/builtin")
TOOL_NAME_RE = re.compile(r'name="([a-zA-Z_][a-zA-Z0-9_]*)"')
BACKTICK_RE = re.compile(r"`([a-zA-Z_][a-zA-Z0-9_]*)`")


def _registered_tool_names() -> set[str]:
    """Collect every tool name declared via @tool(name=...) in builtin tools."""
    names: set[str] = set()
    for path in BUILTIN_TOOLS_DIR.glob("*.py"):
        if path.name == "__init__.py":
            continue
        text = path.read_text()
        for match in TOOL_NAME_RE.finditer(text):
            names.add(match.group(1))
    return names


def _readme_tool_section() -> str:
    """Return the README subsection between the Tools heading and Quick Start."""
    text = README_PATH.read_text()
    match = re.search(
        r"### Tools.*?\n(?P<section>.*?)\n## Quick Start",
        text,
        re.DOTALL,
    )
    if not match:
        pytest.fail("Could not locate Tools section in README.md")
    return match.group("section")


def test_readme_tool_names_are_registered() -> None:
    """Every backtick tool name in the README Tools section is a builtin tool."""
    section = _readme_tool_section()
    readme_names = set(BACKTICK_RE.findall(section))
    registered = _registered_tool_names()

    unknown = readme_names - registered
    if unknown:
        pytest.fail(
            f"README.md Tools section mentions unknown tool names: {sorted(unknown)}"
        )


def test_readme_tool_list_is_not_empty() -> None:
    """The README Tools section must mention at least one tool."""
    section = _readme_tool_section()
    names = BACKTICK_RE.findall(section)
    assert names, "No tool names found in README.md Tools section"


def test_readme_quick_start_contains_required_steps() -> None:
    """The Quick Start section contains the essential bootstrapping commands.

    Quick Start is deliberately split into per-mode blocks (CLI / platforms /
    web), so scan the whole section rather than only the first bash block."""
    text = README_PATH.read_text()
    match = re.search(r"## Quick Start\n(?P<section>.*?)\n## ", text, re.DOTALL)
    if not match:
        pytest.fail("Could not locate Quick Start section in README.md")

    section = match.group("section")
    assert "git clone https://github.com/" in section, (
        "Quick Start must give the real clone URL"
    )
    assert "uv sync" in section, "Quick Start must mention `uv sync`"
    assert "hestia init" in section, "Quick Start must mention `hestia init`"
    assert (
        "hestia serve" in section or "hestia chat" in section
    ), "Quick Start must mention `hestia serve` or `hestia chat`"
