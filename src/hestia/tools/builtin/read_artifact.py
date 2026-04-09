"""Read artifact tool (factory)."""

from typing import Any

from hestia.artifacts.store import ArtifactStore
from hestia.errors import ArtifactExpiredError, ArtifactNotFoundError
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
        max_result_chars=8000,
        auto_artifact_above=100_000,  # Don't recursively artifact
        tags=["artifacts"],
    )
    async def read_artifact(handle: str) -> str:
        """Read an artifact by handle."""
        try:
            content = store.fetch_content(handle)
            return content.decode("utf-8", errors="replace")
        except ArtifactNotFoundError:
            return f"Artifact not found: {handle}"
        except ArtifactExpiredError:
            return f"Artifact expired: {handle}"

    return read_artifact
