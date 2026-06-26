"""Unit tests for browser_login and browser_get tools."""

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hestia.tools.browser.fetch import BrowserFetchResult, ToolResultCategory
from hestia.tools.builtin.browser_get import browser_get
from hestia.tools.builtin.browser_login import browser_login


class MockAsyncContextManager:
    """Mock async context manager for playwright."""

    def __init__(self, enter_value):
        self._enter_value = enter_value

    async def __aenter__(self):
        return self._enter_value

    async def __aexit__(self, *args):
        return None


@pytest.fixture
def mock_playwright():
    """Inject a mock playwright.async_api module into sys.modules."""
    mock_module = SimpleNamespace()
    with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
        yield mock_module


class TestBrowserLogin:
    """Tests for browser_login tool."""

    @pytest.mark.asyncio
    async def test_invalid_url_returns_error(self, mock_playwright):
        """Invalid URL returns error message."""
        mock_playwright.async_playwright = MagicMock()
        result = await browser_login("not-a-url")
        assert "Invalid URL" in result

    @pytest.mark.asyncio
    async def test_missing_scheme_returns_error(self, mock_playwright):
        """URL without scheme returns error message."""
        mock_playwright.async_playwright = MagicMock()
        result = await browser_login("example.com/login")
        assert "Invalid URL" in result

    @pytest.mark.asyncio
    async def test_import_error_when_playwright_not_installed(self):
        """ImportError returns installation instructions."""
        import builtins

        original_import = builtins.__import__

        def _block_playwright(name: str, *args: object, **kwargs: object) -> object:
            if name == "playwright.async_api":
                raise ImportError("No module named 'playwright.async_api'")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", _block_playwright):
            result = await browser_login("https://example.com/login")
        assert "Playwright is not installed" in result

    @pytest.mark.asyncio
    async def test_successful_login_saves_session(self, mock_playwright, tmp_path):
        """Successful login saves cookies and storage state."""
        mock_cookies = [{"name": "session", "value": "abc"}]
        mock_storage = {"cookies": mock_cookies, "origins": []}

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock()

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.storage_state = AsyncMock(return_value=mock_storage)
        mock_context.cookies = AsyncMock(return_value=mock_cookies)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.contexts = []

        mock_playwright_instance = AsyncMock()
        mock_playwright_instance.chromium = AsyncMock()
        mock_playwright_instance.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_playwright.async_playwright = MagicMock(
            return_value=MockAsyncContextManager(mock_playwright_instance)
        )

        with patch(
            "hestia.tools.builtin.browser_login.BrowserSessionStore"
        ) as mock_store_cls:
            mock_store = mock_store_cls.return_value
            result = await browser_login("https://example.com/login")

        assert "Session saved for example.com" in result
        assert "1 cookies stored" in result
        mock_store.save_storage.assert_called_once_with("example.com", mock_storage)
        mock_store.save_cookies.assert_called_once_with("example.com", mock_cookies)


class TestBrowserGet:
    """Tests for browser_get tool."""

    @pytest.fixture
    def mock_fetch_url(self):
        """Patch the shared fetch_url helper used by browser_get."""
        with patch("hestia.tools.builtin.browser_get.fetch_url") as mock_fetch:
            yield mock_fetch

    @pytest.mark.asyncio
    async def test_invalid_url_returns_error(self, mock_fetch_url):
        """Invalid URL returns error message."""
        result = await browser_get("not-a-url")
        assert "Invalid URL" in result
        mock_fetch_url.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_scheme_returns_error(self, mock_fetch_url):
        """URL without scheme returns error message."""
        result = await browser_get("example.com/page")
        assert "Invalid URL" in result
        mock_fetch_url.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delegates_to_fetch_url(self, mock_fetch_url):
        """Successful fetch delegates to shared helper and returns text."""
        mock_fetch_url.return_value = BrowserFetchResult(
            ok=True,
            category=ToolResultCategory.SUCCESS,
            text="Page content here",
            final_url="https://example.com/page",
            title="Example",
        )

        result = await browser_get("https://example.com/page")

        assert result == "Page content here"
        mock_fetch_url.assert_awaited_once_with(
            "https://example.com/page",
            domain="example.com",
            wait_for_selector="",
            wait_seconds=3,
            timeout_seconds=30,
            headless=True,
        )

    @pytest.mark.asyncio
    async def test_passes_wait_for_selector(self, mock_fetch_url):
        """Wait selector is forwarded to shared helper."""
        mock_fetch_url.return_value = BrowserFetchResult(
            ok=True,
            category=ToolResultCategory.SUCCESS,
            text="Content",
            final_url="https://example.com/page",
            title="Example",
        )

        await browser_get(
            "https://example.com/page", wait_for_selector="#content", wait_seconds=5
        )

        mock_fetch_url.assert_awaited_once_with(
            "https://example.com/page",
            domain="example.com",
            wait_for_selector="#content",
            wait_seconds=5,
            timeout_seconds=30,
            headless=True,
        )

    @pytest.mark.asyncio
    async def test_headless_false_passed_through(self, mock_fetch_url):
        """headless=False is forwarded to the shared fetch helper."""
        mock_fetch_url.return_value = BrowserFetchResult(
            ok=True,
            category=ToolResultCategory.SUCCESS,
            text="Headed content",
            final_url="https://example.com/page",
            title="Example",
        )

        result = await browser_get("https://example.com/page", headless=False)

        assert result == "Headed content"
        mock_fetch_url.assert_awaited_once_with(
            "https://example.com/page",
            domain="example.com",
            wait_for_selector="",
            wait_seconds=3,
            timeout_seconds=30,
            headless=False,
        )

    @pytest.mark.asyncio
    async def test_returns_failure_text(self, mock_fetch_url):
        """Blocked result returns the helper's failure text."""
        mock_fetch_url.return_value = BrowserFetchResult(
            ok=False,
            category=ToolResultCategory.BLOCKED,
            text="[BLOCKED - LOGIN_REQUIRED] re-authenticate",
            final_url="https://example.com/login",
            title="Sign in",
        )

        result = await browser_get("https://example.com/page")
        assert "[BLOCKED - LOGIN_REQUIRED]" in result


class TestBrowserSessionHealthCheck:
    """Tests for BrowserSessionStore.check_health."""

    @pytest.mark.asyncio
    async def test_check_health_healthy_page(self, mock_playwright, tmp_path):
        """Healthy page returns 'healthy'."""
        from hestia.tools.browser.session_store import BrowserSessionStore

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.title = AsyncMock(return_value="Dashboard")
        mock_page.url = "https://example.com/dashboard"

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.storage_state = AsyncMock(return_value={"cookies": [], "origins": []})
        mock_context.cookies = AsyncMock(return_value=[])

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        mock_playwright_instance = AsyncMock()
        mock_playwright_instance.chromium = AsyncMock()
        mock_playwright_instance.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_playwright.async_playwright = MagicMock(
            return_value=MockAsyncContextManager(mock_playwright_instance)
        )

        store = BrowserSessionStore(base_dir=tmp_path)
        store.save_cookies("example.com", [{"name": "session", "value": "abc"}])

        status = await store.check_health("example.com")
        assert status == "healthy"

    @pytest.mark.asyncio
    async def test_check_health_login_redirect(self, mock_playwright, tmp_path):
        """Redirect to login page returns 'expired'."""
        from hestia.tools.browser.session_store import BrowserSessionStore

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.title = AsyncMock(return_value="Sign in to Example")
        mock_page.url = "https://example.com/login"

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.storage_state = AsyncMock(return_value={"cookies": [], "origins": []})
        mock_context.cookies = AsyncMock(return_value=[])

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        mock_playwright_instance = AsyncMock()
        mock_playwright_instance.chromium = AsyncMock()
        mock_playwright_instance.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_playwright.async_playwright = MagicMock(
            return_value=MockAsyncContextManager(mock_playwright_instance)
        )

        store = BrowserSessionStore(base_dir=tmp_path)
        store.save_cookies("example.com", [{"name": "session", "value": "abc"}])

        status = await store.check_health("example.com")
        assert status == "expired"

    @pytest.mark.asyncio
    async def test_check_health_rate_limit(self, mock_playwright, tmp_path):
        """Calling check_health too soon raises ValueError."""
        from hestia.tools.browser.session_store import BrowserSessionStore

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.title = AsyncMock(return_value="Dashboard")
        mock_page.url = "https://example.com/dashboard"

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.storage_state = AsyncMock(return_value={"cookies": [], "origins": []})
        mock_context.cookies = AsyncMock(return_value=[])

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        mock_playwright_instance = AsyncMock()
        mock_playwright_instance.chromium = AsyncMock()
        mock_playwright_instance.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_playwright.async_playwright = MagicMock(
            return_value=MockAsyncContextManager(mock_playwright_instance)
        )

        store = BrowserSessionStore(base_dir=tmp_path)
        store.save_cookies("example.com", [{"name": "session", "value": "abc"}])

        # First check should succeed
        await store.check_health("example.com")

        # Second check immediately after should be rate-limited
        with pytest.raises(ValueError, match="rate-limited"):
            await store.check_health("example.com")
