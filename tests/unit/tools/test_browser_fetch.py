"""Tests for shared browser fetch helper."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hestia.tools.browser.fetch import (
    BrowserFetchResult,
    ToolResultCategory,
    fetch_url,
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


@pytest.fixture(autouse=True)
def no_delays() -> Any:
    """Disable rate-limit sleeps and jitter by default."""
    with patch("hestia.tools.browser.fetch._get_min_delay_seconds", return_value=0.0):
        with patch("hestia.tools.browser.fetch.asyncio.sleep", AsyncMock()):
            with patch("hestia.tools.browser.fetch.random.uniform", return_value=0.0):
                yield


@pytest.mark.asyncio
async def test_successful_fetch_returns_text(
    mock_playwright: Any, mock_store: Any
) -> None:
    mock_playwright["page"].evaluate = AsyncMock(return_value="Page content here")

    result = await fetch_url("https://example.com/page", domain="example.com")

    assert isinstance(result, BrowserFetchResult)
    assert result.ok is True
    assert result.category == ToolResultCategory.SUCCESS
    assert result.text == "Page content here"
    assert result.final_url == "https://example.com/page"
    mock_playwright["page"].goto.assert_awaited_once_with(
        "https://example.com/page",
        wait_until="networkidle",
        timeout=30000,
    )
    mock_store.update_metadata.assert_called()


@pytest.mark.asyncio
async def test_login_url_detection_returns_blocked_login(
    mock_playwright: Any, mock_store: Any
) -> None:
    mock_playwright["page"].url = "https://example.com/login?next=/page"
    mock_playwright["page"].title = AsyncMock(return_value="Example")

    result = await fetch_url("https://example.com/page", domain="example.com")

    assert result.ok is False
    assert result.category == ToolResultCategory.BLOCKED
    assert "[BLOCKED - LOGIN_REQUIRED]" in result.text
    assert "login" in result.text.lower()


@pytest.mark.asyncio
async def test_login_title_detection_returns_blocked_login(
    mock_playwright: Any, mock_store: Any
) -> None:
    mock_playwright["page"].url = "https://example.com/page"
    mock_playwright["page"].title = AsyncMock(return_value="Sign in to Example")

    result = await fetch_url("https://example.com/page", domain="example.com")

    assert result.ok is False
    assert result.category == ToolResultCategory.BLOCKED
    assert "[BLOCKED - LOGIN_REQUIRED]" in result.text


@pytest.mark.asyncio
async def test_bot_protection_text_returns_blocked_bot(
    mock_playwright: Any, mock_store: Any
) -> None:
    mock_playwright["page"].evaluate = AsyncMock(
        return_value="Just a moment... additional verification required"
    )

    result = await fetch_url("https://example.com/page", domain="example.com")

    assert result.ok is False
    assert result.category == ToolResultCategory.BLOCKED
    assert "[BLOCKED]" in result.text


@pytest.mark.asyncio
async def test_timeout_returns_timeout(
    mock_playwright: Any, mock_store: Any
) -> None:
    mock_playwright["page"].goto = AsyncMock(side_effect=Exception("Timeout 30000ms exceeded"))

    result = await fetch_url("https://example.com/page", domain="example.com")

    assert result.ok is False
    assert result.category == ToolResultCategory.TIMEOUT
    assert "timeout" in result.text.lower()


@pytest.mark.asyncio
async def test_rate_limiting_sleeps_between_calls(
    mock_playwright: Any, mock_store: Any
) -> None:
    from datetime import UTC, datetime, timedelta

    metadata = MagicMock()
    metadata.last_used = datetime.now(UTC) - timedelta(seconds=0.5)
    mock_store.load_metadata = MagicMock(return_value=metadata)

    with patch("hestia.tools.browser.fetch._get_min_delay_seconds", return_value=2.0):
        with patch("hestia.tools.browser.fetch.asyncio.sleep", AsyncMock()) as mock_sleep:
            with patch("hestia.tools.browser.fetch.random.uniform", return_value=0.25):
                await fetch_url("https://example.com/page", domain="example.com")

    mock_sleep.assert_awaited_once()
    # Sleep should be approximately 2.0 - 0.5 + 0.25 = 1.75
    call_args = mock_sleep.call_args[0]
    assert 1.7 <= call_args[0] <= 1.8


@pytest.mark.asyncio
async def test_extract_links_when_requested(
    mock_playwright: Any, mock_store: Any
) -> None:
    mock_playwright["page"].evaluate = AsyncMock(
        side_effect=[
            "Page with links",
            [
                {"text": "First", "href": "https://example.com/first"},
                {"text": "Second", "href": "https://example.com/second"},
            ],
        ]
    )

    result = await fetch_url(
        "https://example.com/page",
        domain="example.com",
        extract_links=True,
        selector="a",
        pattern="",
    )

    assert result.ok is True
    assert len(result.links) == 2
    assert result.links[0]["href"] == "https://example.com/first"
    assert result.text == "Page with links"
