"""Unit tests for BrowserSessionStore."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hestia.tools.browser.session_store import BrowserSessionStore, SessionMetadata


class _AsyncCtx:
    """Tiny async context manager helper for mocking playwright."""

    def __init__(self, enter_value):
        self._enter_value = enter_value

    async def __aenter__(self):
        return self._enter_value

    async def __aexit__(self, *exc):
        return False


class TestBrowserSessionStore:
    """Tests for BrowserSessionStore."""

    @pytest.fixture
    def store(self, tmp_path):
        return BrowserSessionStore(base_dir=tmp_path)

    def test_save_and_load_cookies(self, store):
        """Cookies can be saved and loaded."""
        cookies = [
            {"name": "session", "value": "abc123", "domain": "example.com"},
            {"name": "user", "value": "dylan", "domain": "example.com"},
        ]
        store.save_cookies("example.com", cookies)
        loaded = store.load_cookies("example.com")
        assert loaded == cookies

    def test_load_cookies_missing_returns_empty(self, store):
        """Loading cookies for unknown domain returns empty list."""
        assert store.load_cookies("unknown.com") == []

    def test_save_and_load_storage_state(self, store):
        """Storage state can be saved and loaded."""
        state = {
            "cookies": [
                {"name": "token", "value": "xyz", "domain": "app.example.com"}
            ],
            "origins": [
                {
                    "origin": "https://app.example.com",
                    "localStorage": [{"name": "theme", "value": "dark"}],
                }
            ],
        }
        store.save_storage("app.example.com", state)
        loaded = store.load_storage("app.example.com")
        assert loaded == state

    def test_load_storage_missing_returns_none(self, store):
        """Loading storage for unknown domain returns None."""
        assert store.load_storage("unknown.com") is None

    def test_list_domains(self, store):
        """list_domains returns normalized, deduplicated domains with session data."""
        store.save_cookies("example.com", [])
        store.save_cookies("sub.example.com", [])
        store.save_storage("another.org", {})

        domains = store.list_domains()
        # sub.example.com normalizes to the eTLD+1 example.com
        assert sorted(domains) == ["another.org", "example.com"]

    def test_list_domains_empty(self, store):
        """list_domains returns empty list when nothing saved."""
        assert store.list_domains() == []

    def test_clear_removes_session(self, store):
        """clear removes all session data for a domain."""
        store.save_cookies("example.com", [{"name": "x", "value": "y"}])
        store.save_storage("example.com", {"key": "value"})

        store.clear("example.com")

        # Check list_domains first because load_cookies/load_storage
        # recreate the session directory via _session_dir().
        assert store.list_domains() == []
        assert store.load_cookies("example.com") == []
        assert store.load_storage("example.com") is None

    def test_clear_unknown_domain_no_error(self, store):
        """clear on unknown domain does not raise."""
        store.clear("nonexistent.com")
        assert store.list_domains() == []

    def test_metadata_roundtrip(self, store):
        """Metadata can be saved and loaded."""
        now = datetime.now(UTC)
        metadata = SessionMetadata(
            domain="example.com",
            created_at=now,
            last_saved=now,
            last_used=now,
            last_health_check=now,
            health_status="healthy",
            health_check_url="https://example.com/dashboard",
            cookie_count=5,
        )
        store.save_metadata("example.com", metadata)
        loaded = store.load_metadata("example.com")
        assert loaded is not None
        assert loaded.domain == "example.com"
        assert loaded.created_at == now
        assert loaded.last_saved == now
        assert loaded.last_used == now
        assert loaded.last_health_check == now
        assert loaded.health_status == "healthy"
        assert loaded.health_check_url == "https://example.com/dashboard"
        assert loaded.cookie_count == 5

    def test_list_sessions_returns_metadata(self, store):
        """list_sessions returns metadata for all domains with session data."""
        store.save_cookies("example.com", [{"name": "a", "value": "b"}])
        store.save_storage("another.org", {"cookies": []})

        sessions = store.list_sessions()
        assert len(sessions) == 2
        domains = {s.domain for s in sessions}
        assert domains == {"example.com", "another.org"}

    def test_clear_removes_metadata(self, store):
        """clear removes metadata along with session data."""
        store.save_cookies("example.com", [{"name": "x", "value": "y"}])
        store.save_metadata("example.com", SessionMetadata(domain="example.com"))

        store.clear("example.com")

        assert store.load_metadata("example.com") is None
        assert store.list_sessions() == []

    def test_update_metadata_patches_fields(self, store):
        """update_metadata creates and patches metadata fields."""
        now = datetime.now(UTC)
        store.update_metadata("example.com", health_status="healthy", cookie_count=3)
        loaded = store.load_metadata("example.com")
        assert loaded is not None
        assert loaded.health_status == "healthy"
        assert loaded.cookie_count == 3

        store.update_metadata("example.com", last_used=now)
        loaded = store.load_metadata("example.com")
        assert loaded is not None
        assert loaded.last_used == now
        assert loaded.health_status == "healthy"
        assert loaded.cookie_count == 3

    def test_save_cookies_updates_metadata(self, store):
        """save_cookies automatically updates last_saved and cookie_count."""
        cookies = [{"name": "a", "value": "b"}, {"name": "c", "value": "d"}]
        store.save_cookies("example.com", cookies)
        metadata = store.load_metadata("example.com")
        assert metadata is not None
        assert metadata.cookie_count == 2
        assert metadata.last_saved is not None

    def test_save_storage_updates_metadata(self, store):
        """save_storage automatically updates last_saved and cookie_count."""
        state = {
            "cookies": [
                {"name": "a", "value": "b"},
                {"name": "c", "value": "d"},
                {"name": "e", "value": "f"},
            ],
            "origins": [],
        }
        store.save_storage("example.com", state)
        metadata = store.load_metadata("example.com")
        assert metadata is not None
        assert metadata.cookie_count == 3
        assert metadata.last_saved is not None

    @pytest.mark.asyncio
    async def test_check_health_rate_limit_throttles_repeated_calls(self, store):
        """check_health refuses automatic re-checks within the one-hour window."""
        now = datetime.now(UTC)
        store.save_metadata(
            "example.com",
            SessionMetadata(
                domain="example.com",
                last_health_check=now,
                health_status="expired",
                health_check_url="https://example.com/",
            ),
        )

        inner = MagicMock()
        inner.chromium.launch = AsyncMock(side_effect=RuntimeError("should not launch"))
        mock_playwright = MagicMock(return_value=_AsyncCtx(inner))

        with (
            patch("playwright.async_api.async_playwright", mock_playwright),
            pytest.raises(ValueError, match="rate-limited"),
        ):
            await store.check_health("example.com")

    @pytest.mark.asyncio
    async def test_check_health_force_bypasses_rate_limit(self, store):
        """force=True bypasses the automatic once-per-hour throttle."""
        now = datetime.now(UTC)
        store.save_cookies("example.com", [{"name": "session", "value": "x"}])
        store.save_metadata(
            "example.com",
            SessionMetadata(
                domain="example.com",
                last_health_check=now,
                health_status="expired",
                health_check_url="https://example.com/",
            ),
        )

        mock_page = AsyncMock()
        mock_page.url = "https://example.com/dashboard"
        mock_page.title = AsyncMock(return_value="Dashboard")
        mock_context = AsyncMock()
        mock_context.cookies = AsyncMock(return_value=[])
        mock_context.storage_state = AsyncMock(return_value={"cookies": [], "origins": []})
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()
        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()
        inner = MagicMock()
        inner.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_playwright = MagicMock(return_value=_AsyncCtx(inner))

        with patch("playwright.async_api.async_playwright", mock_playwright):
            status = await store.check_health("example.com", force=True)

        assert status == "healthy"
