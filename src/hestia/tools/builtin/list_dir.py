"""List directory tool (factory)."""

import asyncio
from pathlib import Path
from typing import Any

from hestia.config import StorageConfig
from hestia.tools.builtin.path_utils import check_path_allowed
from hestia.tools.capabilities import READ_LOCAL
from hestia.tools.metadata import tool


def make_list_dir_tool(config: StorageConfig) -> Any:
    """Create a list_dir tool with path sandboxing."""
    allowed_roots = config.allowed_roots

    @tool(
        name="list_dir",
        public_description="List directory contents. Params: path (str, default '.'), max_entries (int, default 200).",

        tags=["system", "builtin"],
        capabilities=[READ_LOCAL],
    )
    async def list_dir(path: str = ".", max_entries: int = 200) -> str:
        """List files and directories at the given path.

        Returns a formatted listing with file types and sizes.
        Caps output at max_entries to avoid flooding context.
        """
        # Check path sandboxing
        if error := check_path_allowed(path, allowed_roots):
            return error

        target = Path(path)
        if not await asyncio.to_thread(target.is_dir):
            return f"Error: {path} is not a directory"

        all_items = await asyncio.to_thread(lambda: sorted(target.iterdir()))
        entries = []
        for i, item in enumerate(all_items):
            if i >= max_entries:
                entries.append(f"... ({len(all_items) - max_entries} more entries)")
                break
            kind = "dir" if await asyncio.to_thread(item.is_dir) else "file"
            size = ""
            if await asyncio.to_thread(item.is_file):
                size = f" ({(await asyncio.to_thread(item.stat)).st_size} bytes)"
            entries.append(f"  [{kind}] {item.name}{size}")

        if not entries:
            return f"{path}: (empty)"

        return f"{path}:\n" + "\n".join(entries)

    return list_dir
