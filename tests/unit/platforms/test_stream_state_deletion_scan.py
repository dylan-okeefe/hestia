"""Lint: platform code must never delete keys from a dict named ``state``.

The Telegram stream callback closes over a shared ``state`` dict that the
runner also touches between streamed segments. Deleting a key from that dict
(``del state[k]`` or ``state.pop(k)``) made the callback raise
``KeyError: 'message_id'`` on the next streamed chunk and killed the whole
turn mid-tool-loop (fixed in commit 7023e801, which replaced the pop with
``_reset_stream_segment``). This AST scan fails the suite if that shape
reappears anywhere under ``src/hestia/platforms/``.
"""

from __future__ import annotations

import ast
import subprocess
from dataclasses import dataclass
from pathlib import Path

import hestia.platforms

PLATFORMS_DIR = Path(hestia.platforms.__file__).parent
REPO_ROOT = PLATFORMS_DIR.parents[2]

# Justified exceptions, qualified as "<repo-relative path>:<enclosing function>".
# Empty by policy: add an entry only with a comment explaining why the deletion
# cannot race a concurrent reader of the same dict.
ALLOWLIST: list[str] = []


@dataclass
class Violation:
    """One key-deletion on a dict named ``state``."""

    path: Path  # repo-relative (or as given for ad-hoc scans)
    lineno: int
    func: str
    code: str

    @property
    def allowlist_key(self) -> str:
        return f"{self.path.as_posix()}:{self.func}"

    def describe(self) -> str:
        return f"{self.path.as_posix()}:{self.lineno} ({self.func}): {self.code}"


def find_state_key_deletions(path: Path) -> list[Violation]:
    """Scan one source file for ``del state[k]`` and ``state.pop(k``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    def enclosing_func(node: ast.AST) -> str:
        current = parents.get(node)
        while current is not None:
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return current.name
            current = parents.get(current)
        return "<module>"

    violations: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Delete):
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "state"
                ):
                    violations.append(
                        Violation(path, node.lineno, enclosing_func(node), ast.unparse(node))
                    )
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "pop"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "state"
        ):
            violations.append(
                Violation(path, node.lineno, enclosing_func(node), ast.unparse(node))
            )
    violations.sort(key=lambda v: v.lineno)
    return violations


def scan_tree(root: Path) -> list[Violation]:
    """Scan every .py file under *root*, with paths made repo-relative."""
    violations: list[Violation] = []
    for path in sorted(root.rglob("*.py")):
        for violation in find_state_key_deletions(path):
            try:
                violation.path = path.relative_to(REPO_ROOT)
            except ValueError:
                violation.path = path
            violations.append(violation)
    return violations


def test_platforms_never_delete_state_keys() -> None:
    """The current tree must be clean (modulo the allowlist)."""
    offenders = [v for v in scan_tree(PLATFORMS_DIR) if v.allowlist_key not in ALLOWLIST]
    assert not offenders, (
        "Deleting a key from a dict named `state` breaks concurrent readers of the "
        "same dict (see commit 7023e801). Re-seed keys instead, or allowlist with a "
        "justification:\n" + "\n".join(f"  {v.describe()}" for v in offenders)
    )


def test_scan_flags_pre_fix_runners(tmp_path: Path) -> None:
    """The pre-fix runners.py (``state.pop("message_id", None)``) must be flagged.

    Pinned to the parent of the fix commit (5cbce511 = cherry-pick of 7023e801)
    rather than a branch name: ``develop`` no longer contains the pre-fix code
    now that the fix is merged, and the test must keep failing loudly if the
    pinned reference is ever garbage-collected away.
    """
    result = subprocess.run(
        ["git", "show", "5cbce511^:src/hestia/platforms/runners.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    pre_fix = tmp_path / "runners_pre_fix.py"
    pre_fix.write_text(result.stdout, encoding="utf-8")

    violations = find_state_key_deletions(pre_fix)
    assert any(
        "state.pop" in v.code and "message_id" in v.code for v in violations
    ), f"pre-fix runners.py should be flagged, got: {[v.describe() for v in violations]}"
