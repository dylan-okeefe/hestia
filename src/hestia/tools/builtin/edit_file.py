"""Edit file tool (factory)."""

import asyncio
from pathlib import Path
from typing import Any

from hestia.config import StorageConfig
from hestia.tools.builtin.path_utils import check_path_allowed
from hestia.tools.capabilities import EDIT_FILE, WRITE_LOCAL
from hestia.tools.metadata import tool


def make_edit_file_tool(config: StorageConfig) -> Any:
    """Create an edit_file tool with path sandboxing."""
    allowed_roots = config.allowed_roots

    @tool(
        name="edit_file",
        public_description=(
            "Surgically replace a string in an existing file. "
            "Params: path (str), old_string (str), new_string (str). "
            "old_string must match exactly once. Include surrounding context to disambiguate."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative file path. Must be within allowed roots.",
                },
                "old_string": {
                    "type": "string",
                    "description": "Exact text to replace. Must appear exactly once in the file.",
                },
                "new_string": {
                    "type": "string",
                    "description": "Replacement text.",
                },
            },
            "required": ["path", "old_string", "new_string"],
        },
        requires_confirmation=True,
        tags=["system", "builtin"],
        capabilities=[WRITE_LOCAL, EDIT_FILE],
    )
    async def edit_file(path: str = "", old_string: str = "", new_string: str = "") -> str:
        """Replace old_string with new_string in a file.

        old_string must match exactly once in the file.
        Returns a diff preview on success, or an error message.
        """
        if not path:
            return (
                "Error: edit_file requires a 'path' argument. "
                'Example: {"path": "/home/dylan/Documents/file.md", '
                '"old_string": "hello", "new_string": "world"}'
            )
        if not old_string:
            return (
                "Error: edit_file requires an 'old_string' argument. "
                "Provide the exact text you want to replace."
            )

        # Check path sandboxing
        if error := check_path_allowed(path, allowed_roots):
            return error

        target = Path(path)
        if not await asyncio.to_thread(target.exists):
            return f"File not found: {path}"
        if not await asyncio.to_thread(target.is_file):
            return f"Not a file: {path}"

        content = await asyncio.to_thread(target.read_text, encoding="utf-8")
        count = content.count(old_string)
        if count == 0:
            return (
                f"Error: old_string not found in {path}. "
                "Check that the text matches exactly (including whitespace)."
            )
        if count > 1:
            return (
                f"Error: old_string must match exactly once, but found {count} "
                f"occurrences in {path}. "
                "Include more surrounding context to disambiguate."
            )

        new_content = content.replace(old_string, new_string, 1)
        await asyncio.to_thread(target.write_text, new_content, encoding="utf-8")

        # Build a simple diff preview
        old_lines = old_string.splitlines()
        new_lines = new_string.splitlines()
        preview_lines = [f"Edited {path}:"]
        for line in old_lines:
            preview_lines.append(f"  - {line}")
        for line in new_lines:
            preview_lines.append(f"  + {line}")
        return "\n".join(preview_lines)

    return edit_file
