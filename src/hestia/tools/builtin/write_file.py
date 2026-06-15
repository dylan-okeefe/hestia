"""Write file tool (factory)."""

import asyncio
from pathlib import Path
from typing import Any

from hestia.config import StorageConfig
from hestia.tools.builtin.path_utils import check_path_allowed
from hestia.tools.capabilities import WRITE_LOCAL
from hestia.tools.metadata import tool


def make_write_file_tool(
    config: StorageConfig, write_guard_enabled: bool = True
) -> Any:
    """Create a write_file tool with path sandboxing."""
    allowed_roots = config.allowed_roots

    @tool(
        name="write_file",
        public_description=(
            "Write content to a file. Params: path (str), content (str). "
            "If content is longer than 2000 characters, write a short header first "
            "and append the rest with append_to_file."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative file path. Must be within allowed roots.",
                },
                "content": {
                    "type": "string",
                    "description": "Text content to write. MUST be 2000 characters or fewer. For longer documents, write a header and use append_to_file for the rest.",
                    "maxLength": 2000,
                },
            },
            "required": ["path", "content"],
        },
        requires_confirmation=True,
        tags=["system", "builtin"],
        capabilities=[WRITE_LOCAL],
    )
    async def write_file(path: str = "", content: str = "") -> str:
        """Write content to a file at the given path.

        Creates parent directories if they don't exist.
        Refuses to overwrite existing files when write_guard is enabled.
        Returns confirmation with the number of bytes written.
        """
        if not path:
            return (
                "Error: write_file requires a 'path' argument. "
                "Example: {\"path\": \"/home/dylan/Documents/file.md\", \"content\": \"# Hello\"}"
            )
        if not content:
            return (
                "Error: write_file requires a 'content' argument. "
                "Provide the full text content you want to write."
            )

        # Check path sandboxing
        if error := check_path_allowed(path, allowed_roots):
            return error

        target = Path(path)
        if write_guard_enabled and await asyncio.to_thread(target.exists):
            return (
                f"File {path} already exists. "
                "Use edit_file(path=..., old_string=..., new_string=...) instead."
            )

        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(target.write_text, content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"

    return write_file
