"""Write file tool."""

from pathlib import Path

from hestia.tools.metadata import tool


@tool(
    name="write_file",
    public_description="Write content to a file, creating it if it doesn't exist.",
    requires_confirmation=True,
    tags=["system", "builtin"],
)
async def write_file(path: str, content: str) -> str:
    """Write content to a file at the given path.

    Creates parent directories if they don't exist.
    Returns confirmation with the number of bytes written.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return f"Wrote {len(content)} bytes to {path}"
