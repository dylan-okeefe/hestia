"""Tests for browser_interact tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hestia.tools.builtin.browser_interact import (
    _format_actions,
    browser_interact,
)


def _make_mock_locator() -> MagicMock:
    """Return a locator mock with async interaction methods."""
    locator = MagicMock()
    locator.fill = AsyncMock()
    locator.click = AsyncMock()
    locator.select_option = AsyncMock()
    locator.wait_for = AsyncMock()
    locator.press = AsyncMock()
    return locator


class TestFormatActions:
    """Tests for _format_actions."""

    def test_fill_action(self) -> None:
        actions = [{"type": "fill", "selector": "#search", "value": "AI jobs"}]
        assert _format_actions(actions) == "fill(#search='AI jobs')"

    def test_click_action(self) -> None:
        actions = [{"type": "click", "selector": "button[type=submit]"}]
        assert _format_actions(actions) == "click(button[type=submit])"

    def test_multiple_actions(self) -> None:
        actions = [
            {"type": "fill", "selector": "#search", "value": "AI"},
            {"type": "click", "selector": "#submit"},
        ]
        assert _format_actions(actions) == "fill(#search='AI') -> click(#submit)"


@pytest.mark.asyncio
async def test_invalid_url() -> None:
    """An invalid URL returns an error message."""
    result = await browser_interact("not-a-url", actions=[{"type": "click", "selector": "#x"}])
    assert "Invalid URL" in result


@pytest.mark.asyncio
async def test_empty_actions() -> None:
    """Empty actions returns a helpful message."""
    result = await browser_interact("https://example.com", actions=[])
    assert "No actions provided" in result


@pytest.mark.asyncio
async def test_interaction_flow() -> None:
    """The tool launches a browser, performs actions, and returns page text."""
    mock_playwright = MagicMock()
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_page = MagicMock()
    mock_locator = _make_mock_locator()
    mock_page.locator.return_value = mock_locator

    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_page.goto = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value="page text result")
    mock_page.content = AsyncMock(return_value="<html>page</html>")
    mock_context.storage_state = AsyncMock(return_value={})
    mock_context.cookies = AsyncMock(return_value=[])
    mock_context.close = AsyncMock()
    mock_browser.close = AsyncMock()
    mock_playwright.stop = AsyncMock()
    mock_playwright.start = AsyncMock(return_value=mock_playwright)

    with patch(
        "playwright.async_api.async_playwright",
        return_value=mock_playwright,
    ):
        result = await browser_interact(
            "https://example.com",
            actions=[
                {"type": "fill", "selector": "#q", "value": "AI"},
                {"type": "click", "selector": "#search"},
                {"type": "wait", "selector": ".results"},
            ],
            headless=True,
            wait_seconds=1,
        )

    assert result == "page text result"
    mock_page.goto.assert_awaited_once()
    mock_page.locator.assert_any_call("#q")
    mock_page.locator.assert_any_call("#search")
    mock_page.locator.assert_any_call(".results")


@pytest.mark.asyncio
async def test_returns_html_when_requested() -> None:
    """return_html=True returns raw HTML."""
    mock_playwright = MagicMock()
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_page = MagicMock()
    mock_locator = _make_mock_locator()
    mock_page.locator.return_value = mock_locator

    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_page.goto = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.content = AsyncMock(return_value="<html></html>")
    mock_context.storage_state = AsyncMock(return_value={})
    mock_context.cookies = AsyncMock(return_value=[])
    mock_context.close = AsyncMock()
    mock_browser.close = AsyncMock()
    mock_playwright.stop = AsyncMock()
    mock_playwright.start = AsyncMock(return_value=mock_playwright)

    with patch(
        "playwright.async_api.async_playwright",
        return_value=mock_playwright,
    ):
        result = await browser_interact(
            "https://example.com",
            actions=[{"type": "click", "selector": "#go"}],
            return_html=True,
        )

    assert result == "<html></html>"
