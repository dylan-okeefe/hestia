"""HTTP GET tool."""

from hestia.tools.capabilities import NETWORK_EGRESS
from hestia.tools.metadata import tool


@tool(
    name="http_get",
    public_description="Fetch the contents of a URL via HTTP GET.",
    max_inline_chars=6000,
    tags=["network", "builtin"],
    capabilities=[NETWORK_EGRESS],
)
async def http_get(url: str, timeout_seconds: int = 30) -> str:
    """Fetch a URL and return its text content.

    Returns the response body as text, capped by the tool's max_inline_chars.
    Large responses are automatically promoted to artifacts by the registry.
    """
    import httpx

    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout_seconds) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text
