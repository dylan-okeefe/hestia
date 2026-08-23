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
            "Can write documents up to several thousand characters in one call."
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
                    "description": "Text content to write. For very large documents, "
                    "you may still split across multiple write_file or append_to_file calls.",
                    "maxLength": 50000,
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
                "[CATEGORY: transient_other] "
                "Error: write_file requires a 'path' argument. "
                "Example: {\"path\": \"/home/<user>/Documents/file.md\", \"content\": \"# Hello\"}"
            )

        # Check path sandboxing
        if error := check_path_allowed(path, allowed_roots):
            return f"[CATEGORY: transient_other] {error}"

        target = Path(path)
        if write_guard_enabled and await asyncio.to_thread(target.exists):
            return (
                "[CATEGORY: transient_other] "
                f"File {path} already exists. "
                "Use edit_file(path=..., old_string=..., new_string=...) instead."
            )

        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)

        # Atomic write: crash mid-write previously left a truncated file —
        # ironic given ADR-046's purpose. Temp file + os.replace is atomic on
        # POSIX and Windows.
        import os as _os
        import tempfile as _tempfile

        def _atomic_write() -> None:
            fd, tmp_name = _tempfile.mkstemp(
                dir=target.parent, prefix=".write_", suffix=".tmp"
            )
            try:
                with _os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(content)
                _os.replace(tmp_name, target)
            except BaseException:
                try:
                    _os.unlink(tmp_name)
                except OSError:
                    pass
                raise

        await asyncio.to_thread(_atomic_write)
        bytes_written = len(content.encode("utf-8"))
        return f"Wrote {bytes_written} bytes to {path}"

    return write_file
