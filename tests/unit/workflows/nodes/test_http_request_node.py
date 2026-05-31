"""Tests for HttpRequestNode."""

from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch

import httpx
import pytest

from hestia.app import AppContext
from hestia.workflows.models import WorkflowNode
from hestia.workflows.nodes.http_request import HttpRequestNode


@pytest.fixture
def app() -> AppContext:
    return MagicMock(spec=AppContext)  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_get_request(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="http_request",
        label="Fetch",
        config={"url": "https://example.com", "method": "GET"},
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "OK"
    mock_response.headers = {"content-type": "text/html"}

    with patch("httpx.AsyncClient.request", return_value=mock_response) as mock_req:
        executor = HttpRequestNode()
        result = await executor.execute(app, node, {})

    assert result["status"] == 200
    assert result["text"] == "OK"
    mock_req.assert_awaited_once()


@pytest.mark.asyncio
async def test_blocks_ssrf_via_real_transport(app: AppContext) -> None:
    """Workflow node exercises real _is_url_safe + _BLOCKED_RANGES."""
    node = WorkflowNode(
        id="n1",
        type="http_request",
        label="Fetch",
        config={"url": "http://127.0.0.1/secrets"},
    )

    with patch(
        "socket.getaddrinfo",
        return_value=[(socket.AF_INET, 0, 0, "", ("127.0.0.1", 0))],
    ):
        executor = HttpRequestNode()
        with pytest.raises(httpx.ConnectError, match="SSRF blocked"):
            await executor.execute(app, node, {})


@pytest.mark.asyncio
async def test_missing_url_raises(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="http_request",
        label="Fetch",
        config={},
    )
    executor = HttpRequestNode()
    with pytest.raises(ValueError, match="url"):
        await executor.execute(app, node, {})
