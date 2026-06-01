"""Unit tests for browser_login and browser_get tools."""

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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

    @pytest.mark.asyncio
    async def test_invalid_url_returns_error(self, mock_playwright):
        """Invalid URL returns error message."""
        mock_playwright.async_playwright = MagicMock()
        result = await browser_get("not-a-url")
        assert "Invalid URL" in result

    @pytest.mark.asyncio
    async def test_missing_scheme_returns_error(self, mock_playwright):
        """URL without scheme returns error message."""
        mock_playwright.async_playwright = MagicMock()
        result = await browser_get("example.com/page")
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
            result = await browser_get("https://example.com/page")
        assert "Playwright is not installed" in result

    @pytest.mark.asyncio
    async def test_successful_fetch_with_session(self, mock_playwright, tmp_path):
        """Successful fetch reuses stored session and saves refreshed cookies."""
        mock_storage = {
            "cookies": [{"name": "session", "value": "old"}],
            "origins": [],
        }
        mock_text = "Page content here"
        mock_cookies = [{"name": "session", "value": "refreshed"}]

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.wait_for_selector = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=mock_text)

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.cookies = AsyncMock(return_value=mock_cookies)
        mock_context.storage_state = AsyncMock(return_value=mock_storage)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        mock_playwright_instance = AsyncMock()
        mock_playwright_instance.chromium = AsyncMock()
        mock_playwright_instance.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_playwright.async_playwright = MagicMock(
            return_value=MockAsyncContextManager(mock_playwright_instance)
        )

        with patch(
            "hestia.tools.builtin.browser_get.BrowserSessionStore"
        ) as mock_store_cls:
            mock_store = mock_store_cls.return_value
            mock_store.load_storage = MagicMock(return_value=mock_storage)
            mock_store.load_cookies = MagicMock(return_value=[])
            result = await browser_get("https://example.com/page")

        assert result == mock_text
        mock_browser.new_context.assert_called_once_with(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/New_York",
            storage_state=mock_storage,
        )
        mock_store.save_storage.assert_called_once_with("example.com", mock_storage)
        mock_store.save_cookies.assert_called_once_with("example.com", mock_cookies)

    @pytest.mark.asyncio
    async def test_fetch_without_stored_session(self, mock_playwright, tmp_path):
        """Fetch works without stored session."""
        mock_text = "Page content here"
        mock_cookies = []

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=mock_text)

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.cookies = AsyncMock(return_value=mock_cookies)
        mock_context.storage_state = AsyncMock(return_value={"cookies": [], "origins": []})

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        mock_playwright_instance = AsyncMock()
        mock_playwright_instance.chromium = AsyncMock()
        mock_playwright_instance.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_playwright.async_playwright = MagicMock(
            return_value=MockAsyncContextManager(mock_playwright_instance)
        )

        with patch(
            "hestia.tools.builtin.browser_get.BrowserSessionStore"
        ) as mock_store_cls:
            mock_store = mock_store_cls.return_value
            mock_store.load_storage = MagicMock(return_value=None)
            mock_store.load_cookies = MagicMock(return_value=[])
            result = await browser_get("https://example.com/page")

        assert result == mock_text
        mock_browser.new_context.assert_called_once_with(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/New_York",
        )

    @pytest.mark.asyncio
    async def test_fetch_with_wait_for_selector(self, mock_playwright, tmp_path):
        """Fetch respects wait_for_selector parameter."""
        mock_text = "Content after selector"
        mock_cookies = []

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.wait_for_selector = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=mock_text)

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.cookies = AsyncMock(return_value=mock_cookies)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        mock_playwright_instance = AsyncMock()
        mock_playwright_instance.chromium = AsyncMock()
        mock_playwright_instance.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_playwright.async_playwright = MagicMock(
            return_value=MockAsyncContextManager(mock_playwright_instance)
        )

        with patch(
            "hestia.tools.builtin.browser_get.BrowserSessionStore"
        ) as mock_store_cls:
            mock_store = mock_store_cls.return_value
            mock_store.load_storage = MagicMock(return_value=None)
            result = await browser_get(
                "https://example.com/page", wait_for_selector="#content"
            )

        assert result == mock_text
        mock_page.wait_for_selector.assert_awaited_once_with(
            "#content", timeout=30000
        )

    @pytest.mark.asyncio
    async def test_fetch_error_handling(self, mock_playwright, tmp_path):
        """Errors during fetch return error message."""
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(side_effect=Exception("Network error"))
        mock_page.evaluate = AsyncMock(return_value="")

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.storage_state = AsyncMock(return_value={"cookies": [], "origins": []})

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        mock_playwright_instance = AsyncMock()
        mock_playwright_instance.chromium = AsyncMock()
        mock_playwright_instance.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_playwright.async_playwright = MagicMock(
            return_value=MockAsyncContextManager(mock_playwright_instance)
        )

        with patch(
            "hestia.tools.builtin.browser_get.BrowserSessionStore"
        ) as mock_store_cls:
            mock_store = mock_store_cls.return_value
            mock_store.load_storage = MagicMock(return_value=None)
            mock_store.load_cookies = MagicMock(return_value=[])
            result = await browser_get("https://example.com/page")

        assert "Error fetching" in result
        assert "Network error" in result


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
