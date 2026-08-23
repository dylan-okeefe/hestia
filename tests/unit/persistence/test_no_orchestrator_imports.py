"""Lint: persistence modules must not import from hestia.orchestrator."""

import ast
import contextlib
import importlib
from pathlib import Path
from types import ModuleType

import hestia.persistence


def _walk_imports(source: str) -> list[tuple[str, int]]:
    """Return top-level import sources with their line numbers.

    TYPE_CHECKING blocks are excluded because they are not evaluated at
    runtime and are allowed for type hints.
    """
    tree = ast.parse(source)
    type_checking_lines: set[int] = set()

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Name)
            and node.test.id == "TYPE_CHECKING"
        ):
            type_checking_lines.update(
                range(node.lineno, getattr(node, "end_lineno", node.lineno) + 1)
            )

    imports: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if node.lineno in type_checking_lines:
                continue
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append((alias.name, node.lineno))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.append((module, node.lineno))
    return imports


def _discover_persistence_modules() -> list[ModuleType]:
    """Import every submodule under hestia.persistence."""
    package_path = Path(hestia.persistence.__file__).parent
    modules: list[ModuleType] = []

    for path in package_path.rglob("*.py"):
        if path.name.startswith("__"):
            continue
        relative = path.relative_to(package_path.parent)
        module_name = str(relative.with_suffix("")).replace("/", ".").replace("\\", ".")
        with contextlib.suppress(Exception):
            # Unimportable submodules are not the concern of this lint.
            modules.append(importlib.import_module(module_name))

    return modules


def test_persistence_modules_do_not_import_orchestrator():
    """No runtime import in hestia.persistence may target hestia.orchestrator."""
    offenders: list[tuple[str, str, int]] = []

    for module in _discover_persistence_modules():
        try:
            source = Path(module.__file__).read_text(encoding="utf-8")
        except Exception:
            continue

        for imported, lineno in _walk_imports(source):
            if imported.startswith("hestia.orchestrator"):
                offenders.append((module.__name__, imported, lineno))

    assert not offenders, (
        "Persistence modules must not import from hestia.orchestrator:\n"
        + "\n".join(f"  {mod}: {imp!r} (line {line})" for mod, imp, line in offenders)
    )
