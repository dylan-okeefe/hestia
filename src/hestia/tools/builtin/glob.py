"""Glob tool (factory)."""

import asyncio
from pathlib import Path
from typing import Any

from hestia.config import StorageConfig
from hestia.tools.builtin.path_utils import check_path_allowed
from hestia.tools.capabilities import READ_LOCAL
from hestia.tools.metadata import tool

_MAX_RESULTS = 100


def make_glob_tool(config: StorageConfig) -> Any:
    """Create a glob tool with path sandboxing."""
    allowed_roots = config.allowed_roots

    @tool(
        name="glob",
        public_description=(
            "Find files matching a glob pattern. "
            "Params: pattern (str), path (str)."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g. '*.py', '**/*.md').",
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Directory to search in. Must be within allowed roots."
                    ),
                },
            },
            "required": ["pattern"],
        },
        tags=["filesystem"],
        capabilities=[READ_LOCAL],
    )
    async def glob(pattern: str = "", path: str = ".") -> str:
        """Find files matching a glob pattern.

        Returns a newline-separated list of matching paths.
        """
        if not pattern:
            return (
                "Error: glob requires a 'pattern' argument. "
                'Example: {"pattern": "*.py"}'
            )

        if error := check_path_allowed(path, allowed_roots):
            return error

        target = Path(path)
        if not await asyncio.to_thread(target.exists):
            return f"Path not found: {path}"
        if not await asyncio.to_thread(target.is_dir):
            return f"Not a directory: {path}"

        matches: list[str] = []

        def _collect() -> None:
            for p in target.glob(pattern):
                matches.append(str(p))
                if len(matches) >= _MAX_RESULTS:
                    break

        await asyncio.to_thread(_collect)

        if len(matches) >= _MAX_RESULTS:
            matches.append(f"... ({len(matches)}+ matches, truncated)")
        if not matches:
            return f"No matches for pattern '{pattern}' in {path}"
        return "\n".join(matches)

    return glob
