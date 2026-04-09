"""Read file tool."""

from pathlib import Path

from hestia.tools.metadata import tool


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
    max_result_chars=4000,
    auto_artifact_above=3000,
    tags=["filesystem"],
)
async def read_file(path: str, max_bytes: int = 1_000_000) -> str:
    """Read a file and return its contents."""
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
