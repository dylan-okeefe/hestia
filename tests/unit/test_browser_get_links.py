"""Unit tests for browser_get_links tool."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hestia.tools.builtin.browser_get_links import browser_get_links


@pytest.fixture
def mock_playwright() -> Any:
    """Patch playwright.async_api.async_playwright to yield a controllable context."""
    mock_p = MagicMock()
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_page = MagicMock()

    # Set up async context manager chain
    mock_p.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_page.goto = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value=[])
    mock_context.storage_state = AsyncMock(return_value={})
    mock_context.cookies = AsyncMock(return_value=[])
    mock_context.close = AsyncMock()
    mock_browser.close = AsyncMock()

    # patch the async context manager returned by async_playwright()
    async def _playwright_cm():
        return mock_p

    mock_p.__aenter__ = AsyncMock(return_value=mock_p)
    mock_p.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "playwright.async_api.async_playwright",
        return_value=mock_p,
    ):
        yield {
            "p": mock_p,
            "browser": mock_browser,
            "context": mock_context,
            "page": mock_page,
        }


@pytest.mark.asyncio
async def test_extracts_links(mock_playwright: Any) -> None:
    mock_playwright["page"].evaluate.return_value = [
        {"text": "Staff Software Engineer", "href": "https://builtinboston.com/job/123"},
        {"text": "Senior Backend Engineer", "href": "https://builtinboston.com/job/456"},
    ]

    result = await browser_get_links("https://builtinboston.com/jobs")
    assert "Staff Software Engineer" in result
    assert "https://builtinboston.com/job/123" in result
    assert "Senior Backend Engineer" in result
    assert "https://builtinboston.com/job/456" in result

    mock_playwright["page"].goto.assert_awaited_once()
    # Ensure evaluate was called with a single object argument.
    call_args = mock_playwright["page"].evaluate.call_args
    assert isinstance(call_args[0][1], dict)
    assert call_args[0][1]["selector"] == "a"
    assert call_args[0][1]["pattern"] == ""


@pytest.mark.asyncio
async def test_respects_selector_and_pattern(mock_playwright: Any) -> None:
    mock_playwright["page"].evaluate.return_value = []

    await browser_get_links(
        "https://builtinboston.com/jobs",
        selector="a.job-card",
        pattern="Engineer",
    )

    call_args = mock_playwright["page"].evaluate.call_args
    assert call_args[0][1]["selector"] == "a.job-card"
    assert call_args[0][1]["pattern"] == "Engineer"


@pytest.mark.asyncio
async def test_no_links_message(mock_playwright: Any) -> None:
    mock_playwright["page"].evaluate.return_value = []

    result = await browser_get_links("https://example.com")
    assert "No links found" in result
