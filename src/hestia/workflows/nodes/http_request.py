"""HTTP request node with SSRF protection."""

from __future__ import annotations

from typing import Any

import httpx

from hestia.app import AppContext
from hestia.tools.builtin.http_get import SSRFSafeTransport, _is_url_safe
from hestia.workflows.models import WorkflowNode


class HttpRequestNode:
    """Makes an HTTP request with SSRF protection."""

    async def execute(
        self,
        app: AppContext,
        node: WorkflowNode,
        inputs: dict[str, Any],
    ) -> Any:
        """Make an HTTP request.

        Args:
            app: Application context.
            node: The workflow node.
            inputs: Resolved inputs for this node.

        Returns:
            Dict with ``status``, ``text``, and ``headers``.

        Raises:
            ValueError: If the URL is missing or blocked by SSRF rules.
        """
        url = node.config.get("url") or inputs.get("url")
        method = (
            node.config.get("method") or inputs.get("method") or "GET"
        ).upper()
        headers = node.config.get("headers") or inputs.get("headers") or {}
        body = node.config.get("body") or inputs.get("body")
        timeout = (
            node.config.get("timeout_seconds")
            or inputs.get("timeout_seconds")
            or 30
        )

        if not url:
            raise ValueError(
                "HttpRequestNode requires 'url' in config or inputs"
            )

        if error := _is_url_safe(url):
            raise ValueError(f"SSRF blocked: {error}")

        async with httpx.AsyncClient(
            transport=SSRFSafeTransport(),
            follow_redirects=True,
            timeout=timeout,
        ) as client:
            response = await client.request(
                method, url, headers=headers, content=body
            )

        return {
            "status": response.status_code,
            "text": response.text,
            "headers": dict(response.headers),
        }
