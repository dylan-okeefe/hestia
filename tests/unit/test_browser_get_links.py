"""Unit tests for browser_get_links tool."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from hestia.tools.browser.fetch import BrowserFetchResult, ToolResultCategory
from hestia.tools.builtin.browser_get_links import browser_get_links


@pytest.fixture
def mock_fetch_url() -> Any:
    """Patch the shared fetch_url helper used by browser_get_links."""
    with patch("hestia.tools.builtin.browser_get_links.fetch_url") as mock_fetch:
        yield mock_fetch


@pytest.mark.asyncio
async def test_extracts_links(mock_fetch_url: Any) -> None:
    mock_fetch_url.return_value = BrowserFetchResult(
        ok=True,
        category=ToolResultCategory.SUCCESS,
        text="",
        links=[
            {"text": "Staff Software Engineer", "href": "https://builtinboston.com/job/123"},
            {"text": "Senior Backend Engineer", "href": "https://builtinboston.com/job/456"},
        ],
        final_url="https://builtinboston.com/jobs",
        title="Jobs",
    )

    result = await browser_get_links("https://builtinboston.com/jobs")

    assert "Staff Software Engineer" in result
    assert "https://builtinboston.com/job/123" in result
    assert "Senior Backend Engineer" in result
    assert "https://builtinboston.com/job/456" in result

    mock_fetch_url.assert_awaited_once_with(
        "https://builtinboston.com/jobs",
        domain="builtinboston.com",
        selector="a",
        extract_links=True,
        pattern="",
        wait_seconds=3,
        timeout_seconds=60,
    )


@pytest.mark.asyncio
async def test_respects_selector_and_pattern(mock_fetch_url: Any) -> None:
    mock_fetch_url.return_value = BrowserFetchResult(
        ok=True,
        category=ToolResultCategory.SUCCESS,
        text="",
        links=[],
        final_url="https://builtinboston.com/jobs",
        title="Jobs",
    )

    await browser_get_links(
        "https://builtinboston.com/jobs",
        selector="a.job-card",
        pattern="Engineer",
    )

    mock_fetch_url.assert_awaited_once_with(
        "https://builtinboston.com/jobs",
        domain="builtinboston.com",
        selector="a.job-card",
        extract_links=True,
        pattern="Engineer",
        wait_seconds=3,
        timeout_seconds=60,
    )


@pytest.mark.asyncio
async def test_no_links_message(mock_fetch_url: Any) -> None:
    mock_fetch_url.return_value = BrowserFetchResult(
        ok=True,
        category=ToolResultCategory.SUCCESS,
        text="",
        links=[],
        final_url="https://example.com",
        title="Example",
    )

    result = await browser_get_links("https://example.com")
    assert "No links found" in result


@pytest.mark.asyncio
async def test_returns_failure_text_when_blocked(mock_fetch_url: Any) -> None:
    mock_fetch_url.return_value = BrowserFetchResult(
        ok=False,
        category=ToolResultCategory.BLOCKED,
        text="[BLOCKED - LOGIN_REQUIRED] re-authenticate",
        final_url="https://example.com/login",
        title="Sign in",
    )

    result = await browser_get_links("https://example.com")
    assert "[BLOCKED - LOGIN_REQUIRED]" in result
