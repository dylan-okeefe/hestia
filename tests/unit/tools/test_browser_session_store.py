"""Unit tests for BrowserSessionStore."""

import pytest

from hestia.tools.browser.session_store import BrowserSessionStore


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
        """list_domains returns saved domain names."""
        store.save_cookies("example.com", [])
        store.save_cookies("sub.example.com", [])
        store.save_storage("another.org", {})

        domains = store.list_domains()
        assert sorted(domains) == ["another.org", "example.com", "sub.example.com"]

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
