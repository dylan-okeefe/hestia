"""Write file tool (factory)."""

from pathlib import Path
from typing import Any

from hestia.config import StorageConfig
from hestia.tools.builtin.path_utils import check_path_allowed
from hestia.tools.capabilities import WRITE_LOCAL
from hestia.tools.metadata import tool


def make_write_file_tool(config: StorageConfig, **kw: Any) -> Any:
    """Create a write_file tool with path sandboxing."""
    allowed_roots = config.allowed_roots

    @tool(
        name="write_file",
        public_description="Write content to a file. Params: path (str), content (str).",

        requires_confirmation=True,
        tags=["system", "builtin"],
        capabilities=[WRITE_LOCAL],
    )
    async def write_file(path: str, content: str) -> str:
        """Write content to a file at the given path.

        Creates parent directories if they don't exist.
        Returns confirmation with the number of bytes written.
        """
        # Check path sandboxing
        if error := check_path_allowed(path, allowed_roots):
            return error

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"

    return write_file
