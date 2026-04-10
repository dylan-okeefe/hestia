"""List directory tool."""

from pathlib import Path

from hestia.tools.metadata import tool


@tool(
    name="list_dir",
    public_description="List the contents of a directory.",
    tags=["system", "builtin"],
)
async def list_dir(path: str = ".", max_entries: int = 200) -> str:
    """List files and directories at the given path.

    Returns a formatted listing with file types and sizes.
    Caps output at max_entries to avoid flooding context.
    """
    target = Path(path)
    if not target.is_dir():
        return f"Error: {path} is not a directory"

    all_items = sorted(target.iterdir())
    entries = []
    for i, item in enumerate(all_items):
        if i >= max_entries:
            entries.append(f"... ({len(all_items) - max_entries} more entries)")
            break
        kind = "dir" if item.is_dir() else "file"
        size = ""
        if item.is_file():
            size = f" ({item.stat().st_size} bytes)"
        entries.append(f"  [{kind}] {item.name}{size}")

    if not entries:
        return f"{path}: (empty)"

    return f"{path}:\n" + "\n".join(entries)
