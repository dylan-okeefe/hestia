"""Read file tool (factory)."""

import asyncio
from pathlib import Path
from typing import Any

from hestia.config import StorageConfig
from hestia.tools.builtin.path_utils import check_path_allowed
from hestia.tools.capabilities import READ_LOCAL
from hestia.tools.metadata import tool


def make_read_file_tool(config: StorageConfig) -> Any:
    """Create a read_file tool with path sandboxing."""
    allowed_roots = config.allowed_roots

    @tool(
        name="read_file",
        public_description=(
            "Read the contents of a local text file. "
            "Files larger than 4000 characters are stored as artifacts; "
            "use read_artifact(handle, start_at=4000, length=4000) to read the rest in chunks."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file"},
                "max_bytes": {
                    "type": "integer",
                    "description": "Max bytes to read (default 1MB)",
                },
            },
            "required": ["path"],
        },
        max_inline_chars=4000,
        tags=["filesystem"],
        capabilities=[READ_LOCAL],
    )
    async def read_file(path: str = "", max_bytes: int = 1_000_000) -> str:
        """Read a file and return its contents."""
        if not path:
            return (
                "Error: read_file requires a 'path' argument. "
                'Example: {"path": "/home/<user>/Documents/file.md"}'
            )
        # Check path sandboxing
        if error := check_path_allowed(path, allowed_roots):
            return error

        p = Path(path)
        if not await asyncio.to_thread(p.exists):
            return f"File not found: {path}"
        if not await asyncio.to_thread(p.is_file):
            return f"Not a file: {path}"
        # PERF-011: read at most max_bytes from disk. Loading the whole file
        # first made a multi-GB file an OOM vector.
        def _read_bounded() -> bytes:
            with p.open("rb") as fh:
                return fh.read(max_bytes)

        data = await asyncio.to_thread(_read_bounded)
        truncated_note = (
            f"\n[truncated at {max_bytes} bytes]" if len(data) >= max_bytes else ""
        )
        try:
            return data.decode("utf-8") + truncated_note
        except UnicodeDecodeError:
            return f"Binary file ({len(data)} bytes). Not decoded.{truncated_note}"

    return read_file
