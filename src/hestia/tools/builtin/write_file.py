"""Write file tool (factory)."""

from pathlib import Path
from typing import Any

from hestia.tools.builtin.path_utils import check_path_allowed
from hestia.tools.capabilities import WRITE_LOCAL
from hestia.tools.metadata import tool


def make_write_file_tool(allowed_roots: list[str]) -> Any:
    """Create a write_file tool with path sandboxing.

    Args:
        allowed_roots: List of allowed root directories

    Returns:
        The write_file tool function
    """

    @tool(
        name="write_file",
        public_description="Write content to a file, creating it if it doesn't exist.",
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
        target.write_text(content)
        return f"Wrote {len(content)} bytes to {path}"

    return write_file


# Default write_file for backward compatibility (no sandboxing)
# This will be replaced by the factory-created tool in cli.py
async def _default_write_file(path: str, content: str) -> str:
    """Default write_file without sandboxing (for backward compatibility)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return f"Wrote {len(content)} bytes to {path}"


# Create a tool with no sandboxing for backward compatibility
write_file = tool(
    name="write_file",
    public_description="Write content to a file, creating it if it doesn't exist.",
    requires_confirmation=True,
    tags=["system", "builtin"],
    capabilities=[WRITE_LOCAL],
)(_default_write_file)
