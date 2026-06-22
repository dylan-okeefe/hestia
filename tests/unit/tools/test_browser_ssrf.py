"""Tests for browser SSRF protection using the shared ssrf helpers."""

from __future__ import annotations

import socket
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hestia.tools.browser.fetch import BrowserFetchResult, ToolResultCategory, fetch_url
from hestia.tools.builtin.http_get import http_get

# Reuse the autouse browser-mocking fixtures from the browser fetch test module.
from tests.unit.tools.test_browser_fetch import (  # noqa: F401
    isolated_browser_pool,
    no_delays,
)


@pytest.fixture
def mock_playwright() -> Any:
    """Patch playwright.async_api.async_playwright to yield a controllable context."""
    mock_p = MagicMock()
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_page = MagicMock()

    mock_p.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_page.goto = AsyncMock()
    mock_page.wait_for_selector = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.title = AsyncMock(return_value="Example")
    mock_page.url = "https://example.com/page"
    mock_page.evaluate = AsyncMock(return_value="")
    mock_context.storage_state = AsyncMock(return_value={"cookies": [], "origins": []})
    mock_context.cookies = AsyncMock(return_value=[])
    mock_context.close = AsyncMock()
    mock_browser.close = AsyncMock()

    mock_p.__aenter__ = AsyncMock(return_value=mock_p)
    mock_p.__aexit__ = AsyncMock(return_value=False)

    with patch("hestia.tools.browser.fetch.async_playwright", return_value=mock_p):
        yield {
            "p": mock_p,
            "browser": mock_browser,
            "context": mock_context,
            "page": mock_page,
        }


@pytest.fixture
def mock_store() -> Any:
    """Patch BrowserSessionStore in fetch module."""
    with patch("hestia.tools.browser.fetch.BrowserSessionStore") as mock_store_cls:
        mock_instance = MagicMock()
        mock_instance.load_metadata = MagicMock(return_value=None)
        mock_instance.load_storage = MagicMock(return_value=None)
        mock_instance.load_cookies = MagicMock(return_value=[])
        mock_instance.update_metadata = MagicMock(return_value=None)
        mock_instance.save_storage = MagicMock()
        mock_instance.save_cookies = MagicMock()
        mock_store_cls.return_value = mock_instance
        yield mock_instance


@pytest.mark.asyncio
async def test_fetch_url_blocks_loopback(mock_playwright: Any, mock_store: Any) -> None:
    """fetch_url must block loopback addresses before launching a browser."""
    result = await fetch_url("http://127.0.0.1:8001", domain="example.com")

    assert isinstance(result, BrowserFetchResult)
    assert result.ok is False
    assert result.category == ToolResultCategory.BLOCKED
    assert "[CATEGORY: BLOCKED]" in result.text
    assert "SSRF blocked" in result.text
    mock_playwright["browser"].launch.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_url_blocks_cloud_metadata(
    mock_playwright: Any, mock_store: Any
) -> None:
    """fetch_url must block the cloud metadata endpoint before launching a browser."""
    result = await fetch_url("http://169.254.169.254", domain="example.com")

    assert isinstance(result, BrowserFetchResult)
    assert result.ok is False
    assert result.category == ToolResultCategory.BLOCKED
    assert "[CATEGORY: BLOCKED]" in result.text
    assert "SSRF blocked" in result.text
    mock_playwright["browser"].launch.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_url_allows_public_url(
    mock_playwright: Any, mock_store: Any
) -> None:
    """Public URLs proceed through the browser fetch as usual."""
    with patch(
        "hestia.security.ssrf.socket.getaddrinfo",
        return_value=[(socket.AF_INET, 0, 0, "", ("93.184.216.34", 0))],
    ):
        result = await fetch_url("https://example.com/page", domain="example.com")

    assert isinstance(result, BrowserFetchResult)
    assert result.ok is True
    assert result.category == ToolResultCategory.SUCCESS
    mock_playwright["page"].goto.assert_awaited_once_with(
        "https://example.com/page",
        wait_until="domcontentloaded",
        timeout=30000,
    )


@pytest.mark.asyncio
async def test_http_get_blocks_loopback() -> None:
    """http_get must block loopback URLs via the shared helper without egress."""
    with patch("hestia.tools.builtin.http_get.httpx.AsyncClient") as mock_client:
        result = await http_get("http://127.0.0.1:8001/")

    assert "SSRF blocked" in result
    mock_client.assert_not_called()


@pytest.mark.asyncio
async def test_http_get_blocks_private_ip() -> None:
    """http_get must block RFC1918 private URLs via the shared helper."""
    with patch("hestia.tools.builtin.http_get.httpx.AsyncClient") as mock_client:
        result = await http_get("http://192.168.1.1/secret")

    assert "SSRF blocked" in result
    mock_client.assert_not_called()
