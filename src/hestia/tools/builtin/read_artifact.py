"""Read artifact tool (factory)."""

import asyncio
from typing import Any

from hestia.artifacts.store import ArtifactStore
from hestia.errors import ArtifactExpiredError, ArtifactNotFoundError
from hestia.tools.capabilities import READ_LOCAL
from hestia.tools.metadata import tool


def make_read_artifact_tool(store: ArtifactStore) -> Any:
    """Create a read_artifact tool that closes over the artifact store.

    This is a factory because the tool needs access to the ArtifactStore instance.
    """

    @tool(
        name="read_artifact",
        public_description=(
            "Read a chunk of an artifact by its handle. "
            "After a read_file preview, use start_at=4000 to continue reading "
            "the remaining content in chunks."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "handle": {
                    "type": "string",
                    "description": "Artifact handle (art_xxxxxxxxxx)",
                },
                "artifact": {
                    "type": "string",
                    "description": (
                        "Alias for handle. Accepts an artifact handle or a full "
                        "path like .../art_xxxxxxxxxx.bin."
                    ),
                },
                "start_at": {
                    "type": "integer",
                    "description": "Byte offset to start reading from (default 0)",
                    "default": 0,
                },
                "length": {
                    "type": "integer",
                    "description": "Maximum bytes to return (default 4000)",
                    "default": 4000,
                },
            },
            "required": [],
        },
        max_inline_chars=8000,
        tags=["artifacts"],
        capabilities=[READ_LOCAL],
    )
    async def read_artifact(
        handle: str | None = None,
        artifact: str | None = None,
        start_at: int = 0,
        length: int = 4000,
    ) -> str:
        """Read a chunk of an artifact by handle.

        ``ArtifactStore.fetch_content`` is synchronous and may touch the
        filesystem; we offload it via ``asyncio.to_thread`` so the event
        loop stays responsive for concurrent tool dispatch.
        """
        raw_handle = handle or artifact
        if not raw_handle:
            return "Error: read_artifact requires either handle or artifact."

        # Normalize full paths like .../art_xxxxxxxxxx.bin to the bare handle.
        normalized = str(raw_handle)
        if "/" in normalized or "\\" in normalized:
            normalized = normalized.replace("\\", "/").split("/")[-1]
        if normalized.endswith(".bin"):
            normalized = normalized[:-4]

        try:
            content = await asyncio.to_thread(store.fetch_content, normalized)
            text = content.decode("utf-8", errors="replace")
        except ArtifactNotFoundError:
            return f"Artifact not found: {normalized}"
        except ArtifactExpiredError:
            return f"Artifact expired: {normalized}"

        total = len(text)
        if start_at < 0:
            start_at = 0
        if start_at >= total:
            return f"[artifact {normalized}: offset {start_at} is past end of {total} chars]"

        end = min(start_at + length, total)
        chunk = text[start_at:end]
        return (
            f"[artifact {normalized}: bytes {start_at}-{end} of {total}]\n\n{chunk}"
        )

    return read_artifact
