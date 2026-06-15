"""Append to file tool (factory)."""

import asyncio
from pathlib import Path
from typing import Any

from hestia.config import StorageConfig
from hestia.tools.builtin.path_utils import check_path_allowed
from hestia.tools.capabilities import WRITE_LOCAL
from hestia.tools.metadata import tool


def make_append_to_file_tool(config: StorageConfig) -> Any:
    """Create an append_to_file tool with path sandboxing."""
    allowed_roots = config.allowed_roots

    @tool(
        name="append_to_file",
        public_description=(
            "Append content to an existing file. Params: path (str), content (str). "
            "If content is longer than 2000 characters, append it in sections using "
            "multiple append_to_file calls after creating the file with write_file."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Absolute or relative file path. "
                        "Must be within allowed roots."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "Text content to append. MUST be 2000 characters or fewer. Append in sections.",
                    "maxLength": 2000,
                },
            },
            "required": ["path", "content"],
        },
        requires_confirmation=True,
        tags=["system", "builtin"],
        capabilities=[WRITE_LOCAL],
    )
    async def append_to_file(path: str = "", content: str = "") -> str:
        """Append content to a file at the given path.

        Creates the file (and parent directories) if they don't exist.
        Returns confirmation with the number of bytes appended.
        """
        if not path:
            return (
                "Error: append_to_file requires a 'path' argument. "
                'Example: {"path": "/home/<user>/Documents/file.md", "content": "more text"}'
            )
        if not content:
            return (
                "Error: append_to_file requires a 'content' argument. "
                "Provide the text content you want to append."
            )

        # Check path sandboxing
        if error := check_path_allowed(path, allowed_roots):
            return error

        target = Path(path)
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)

        def _append() -> None:
            with open(target, "a", encoding="utf-8") as f:
                f.write(content)

        await asyncio.to_thread(_append)
        return f"Appended {len(content)} bytes to {path}"

    return append_to_file
