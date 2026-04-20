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
        public_description="Retrieve the full content of an artifact by its handle.",
        parameters_schema={
            "type": "object",
            "properties": {
                "handle": {
                    "type": "string",
                    "description": "Artifact handle (art_xxxxxxxxxx)",
                }
            },
            "required": ["handle"],
        },
        max_inline_chars=8000,
        tags=["artifacts"],
        capabilities=[READ_LOCAL],
    )
    async def read_artifact(handle: str) -> str:
        """Read an artifact by handle.

        ``ArtifactStore.fetch_content`` is synchronous and may touch the
        filesystem; we offload it via ``asyncio.to_thread`` so the event
        loop stays responsive for concurrent tool dispatch (Copilot C-3).
        """
        try:
            content = await asyncio.to_thread(store.fetch_content, handle)
            return content.decode("utf-8", errors="replace")
        except ArtifactNotFoundError:
            return f"Artifact not found: {handle}"
        except ArtifactExpiredError:
            return f"Artifact expired: {handle}"

    return read_artifact
