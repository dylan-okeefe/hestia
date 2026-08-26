"""D4: every @tool declaration in tools/builtin reaches the registry.

A declared-but-never-registered tool imports cleanly, type-checks, and is
simply invisible to the model - invisible to every gate until now.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("HESTIA_ALLOW_DUMMY_MODEL", "1")

from hestia.app import AppContext  # noqa: E402
from hestia.config import HestiaConfig  # noqa: E402


def _declared_tool_names() -> set[str]:
    """Names from @tool(name="...") literals across tools/builtin/*.py."""
    import ast

    builtin = Path(__file__).resolve().parents[2] / "src" / "hestia" / "tools" / "builtin"
    names: set[str] = set()
    for path in builtin.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not (isinstance(dec, ast.Call) and getattr(dec.func, "id", "") == "tool"):
                    continue
                for kw in dec.keywords:
                    if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                        names.add(str(kw.value.value))
    return names


@pytest.fixture
def registered_names(tmp_path) -> set[str]:
    cfg = HestiaConfig.default()
    cfg.storage.database_url = "sqlite+aiosqlite:///:memory:"
    cfg.storage.artifacts_dir = tmp_path / "artifacts"
    # Enable every conditional family so conditional registrations happen:
    # email needs hosts + an adapter; web_search needs provider + api_key.
    cfg.email.imap_host = "imap.example.com"
    cfg.email.smtp_host = "smtp.example.com"
    cfg.email.password = "test"
    cfg.web_search.provider = "tavily"
    cfg.web_search.api_key = "test-key"
    app = AppContext(cfg)
    app.register_tools()
    return set(app.tool_registry.list_names())


def test_every_declared_builtin_tool_is_registered(registered_names) -> None:
    declared = _declared_tool_names()
    assert declared, "no @tool declarations found - AST scan broken?"
    missing = sorted(declared - registered_names - EXCLUDED_BUILTIN_TOOLS)
    assert not missing, (
        f"{len(missing)} declared builtin tools never reach the registry: "
        f"{missing}. Register them or add to EXCLUDED_BUILTIN_TOOLS with a "
        "reason."
    )


# search_web declares itself but was never wired into register_tools; the
# model uses web_search. Whether to light it up is a product decision - it
# stays excluded (and invisible) until then.
EXCLUDED_BUILTIN_TOOLS: set[str] = {"search_web"}


def test_exclusions_are_declared_tools(registered_names) -> None:
    """The escape hatch may only hide tools that actually exist."""
    assert _declared_tool_names() >= EXCLUDED_BUILTIN_TOOLS
