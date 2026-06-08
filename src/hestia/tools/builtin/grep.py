"""Grep tool (factory)."""

import asyncio
import re
from pathlib import Path
from typing import Any

from hestia.config import StorageConfig
from hestia.tools.builtin.path_utils import check_path_allowed
from hestia.tools.capabilities import READ_LOCAL
from hestia.tools.metadata import tool

_MAX_RESULTS = 100


def make_grep_tool(config: StorageConfig) -> Any:
    """Create a grep tool with path sandboxing."""
    allowed_roots = config.allowed_roots

    @tool(
        name="grep",
        public_description=(
            "Search file contents with regex. "
            "Params: pattern (str), path (str), include (list[str])."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regular expression pattern to search for.",
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Directory to search in. Must be within allowed roots."
                    ),
                },
                "include": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional file extensions to include (e.g. ['.py', '.js'])."
                    ),
                },
            },
            "required": ["pattern"],
        },
        tags=["filesystem"],
        capabilities=[READ_LOCAL],
    )
    async def grep(
        pattern: str = "", path: str = ".", include: list[str] | None = None
    ) -> str:
        """Search file contents for lines matching a regex pattern.

        Returns matching lines in ``file:line:content`` format.
        """
        if not pattern:
            return (
                "Error: grep requires a 'pattern' argument. "
                'Example: {"pattern": "def "}'
            )

        if error := check_path_allowed(path, allowed_roots):
            return error

        target = Path(path)
        if not await asyncio.to_thread(target.exists):
            return f"Path not found: {path}"
        if not await asyncio.to_thread(target.is_dir):
            return f"Not a directory: {path}"

        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return f"Invalid regex pattern: {exc}"

        if isinstance(include, str):
            include = [include]

        matches: list[str] = []

        def _walk() -> None:
            for file_path in target.rglob("*"):
                if not file_path.is_file():
                    continue
                if include is not None and file_path.suffix not in include:
                    continue
                try:
                    text = file_path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    if regex.search(line):
                        matches.append(f"{file_path}:{i}:{line.rstrip()}")
                        if len(matches) >= _MAX_RESULTS:
                            return

        await asyncio.to_thread(_walk)

        if len(matches) >= _MAX_RESULTS:
            matches.append(f"... (truncated after {_MAX_RESULTS} matches)")
        if not matches:
            return f"No matches for pattern '{pattern}' in {path}"
        return "\n".join(matches)

    return grep
