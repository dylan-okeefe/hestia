"""Read file tool (factory)."""

from pathlib import Path
from typing import Any

from hestia.tools.builtin.path_utils import check_path_allowed
from hestia.tools.capabilities import READ_LOCAL
from hestia.tools.metadata import tool


def make_read_file_tool(allowed_roots: list[str]) -> Any:
    """Create a read_file tool with path sandboxing."""

    @tool(
        name="read_file",
        public_description=(
            "Read the contents of a local text file. Large files are stored as artifacts."
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
    async def read_file(path: str, max_bytes: int = 1_000_000) -> str:
        """Read a file and return its contents."""
        # Check path sandboxing
        if error := check_path_allowed(path, allowed_roots):
            return error

        p = Path(path)
        if not p.exists():
            return f"File not found: {path}"
        if not p.is_file():
            return f"Not a file: {path}"
        data = p.read_bytes()[:max_bytes]
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return f"Binary file ({len(data)} bytes). Not decoded."

    return read_file
