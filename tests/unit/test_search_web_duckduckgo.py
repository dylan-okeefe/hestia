"""Unit tests for DuckDuckGo search_web fallback tool."""


# The search_web submodule is shadowed by the search_web function in
# hestia.tools.builtin.__init__, so we must load the actual module via
# importlib to monkeypatch module-level names.
import importlib

import pytest

from hestia.tools.builtin.search_web import (
    _RESULT_RE,
    _strip_tags,
    _unescape,
    search_web,
)

_search_web_module = importlib.import_module("hestia.tools.builtin.search_web")


class TestStripTags:
    """Tests for _strip_tags helper."""

    def test_removes_simple_tags(self):
        """Basic HTML tags are stripped."""
        assert _strip_tags("<b>hello</b>") == "hello"

    def test_removes_nested_tags(self):
        """Nested tags are fully stripped."""
        assert _strip_tags("<div><span>text</span></div>") == "text"

    def test_empty_string(self):
        """Empty string stays empty."""
        assert _strip_tags("") == ""

    def test_no_tags(self):
        """String without tags is unchanged."""
        assert _strip_tags("plain text") == "plain text"

    def test_self_closing_tag(self):
        """Self-closing tags are stripped."""
        assert _strip_tags("line<br/>break") == "linebreak"


class TestUnescape:
    """Tests for _unescape helper."""

    def test_decodes_html_entities(self):
        """Common entities are decoded."""
        assert _unescape("Tom &amp; Jerry") == "Tom & Jerry"

    def test_decodes_quotes(self):
        """Quote entities are decoded."""
        assert _unescape("&quot;hello&quot;") == '"hello"'

    def test_no_entities(self):
        """String without entities is unchanged."""
        assert _unescape("no entities here") == "no entities here"


class TestResultRegex:
    """Tests for the DuckDuckGo HTML result regex."""

    def test_matches_typical_result(self):
        """Regex extracts title, redirect, URL, and snippet from typical HTML."""
        html = (
            '<a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com">'
            '<b>Example Title</b></a>'
            '<a class="result__url" href="/l/?uddg=https%3A%2F%2Fexample.com">'
            'example.com</a>'
            '<a class="result__snippet">This is a snippet.</a>'
        )
        matches = _RESULT_RE.findall(html)
        assert len(matches) == 1
        redirect, title, url, snippet = matches[0]
        assert "uddg=" in redirect
        assert "Example Title" in title
        assert "example.com" in url
        assert "snippet" in snippet

    def test_no_match_on_empty_html(self):
        """Empty HTML returns no matches."""
        assert _RESULT_RE.findall("") == []

    def test_no_match_on_malformed_html(self):
        """Malformed result blocks are skipped."""
        html = '<div class="result__a">No link here</div>'
        assert _RESULT_RE.findall(html) == []


class TestSearchWebLogic:
    """Tests for search_web result-processing logic (parsing + formatting)."""

    @pytest.mark.asyncio
    async def test_empty_results_page(self, monkeypatch):
        """HTML with no result blocks returns 'No results found.'"""

        async def fake_http_get(url: str, **kwargs):
            return "<html><body>No results</body></html>"

        monkeypatch.setattr(
            _search_web_module, "http_get", fake_http_get
        )
        result = await search_web("test query")
        assert result == "No results found."

    @pytest.mark.asyncio
    async def test_filters_ad_results(self, monkeypatch):
        """Ad redirects (y.js with ad_domain) are skipped."""

        async def fake_http_get(url: str, **kwargs):
            return (
                '<a class="result__a" href="/y.js?ad_domain=example.com">'
                '<b>Ad Title</b></a>'
                '<a class="result__url" href="/y.js?ad_domain=example.com">'
                'example.com</a>'
                '<a class="result__snippet">Buy now!</a>'
                '<a class="result__a" href="/l/?uddg=https%3A%2F%2Freal.com">'
                '<b>Real Title</b></a>'
                '<a class="result__url" href="/l/?uddg=https%3A%2F%2Freal.com">'
                'real.com</a>'
                '<a class="result__snippet">Real snippet.</a>'
            )

        monkeypatch.setattr(
            _search_web_module, "http_get", fake_http_get
        )
        result = await search_web("test query")
        assert "Ad Title" not in result
        assert "Real Title" in result
        assert "https://real.com" in result

    @pytest.mark.asyncio
    async def test_deduplicates_urls(self, monkeypatch):
        """Duplicate URLs only appear once."""

        async def fake_http_get(url: str, **kwargs):
            block = (
                '<a class="result__a" href="/l/?uddg=https%3A%2F%2Fdup.com">'
                '<b>Title</b></a>'
                '<a class="result__url" href="/l/?uddg=https%3A%2F%2Fdup.com">'
                'dup.com</a>'
                '<a class="result__snippet">Snippet.</a>'
            )
            return block + block  # duplicate

        monkeypatch.setattr(
            _search_web_module, "http_get", fake_http_get
        )
        result = await search_web("test query")
        assert result.count("https://dup.com") == 1

    @pytest.mark.asyncio
    async def test_max_results_clamping(self, monkeypatch):
        """max_results is clamped to 1-10."""

        async def fake_http_get(url: str, **kwargs):
            blocks = []
            for i in range(15):
                blocks.append(
                    f'<a class="result__a" href="/l/?uddg=https%3A%2F%2Fsite{i}.com">'
                    f'<b>Title {i}</b></a>'
                    f'<a class="result__url" href="/l/?uddg=https%3A%2F%2Fsite{i}.com">'
                    f'site{i}.com</a>'
                    f'<a class="result__snippet">Snippet {i}.</a>'
                )
            return "".join(blocks)

        monkeypatch.setattr(
            _search_web_module, "http_get", fake_http_get
        )
        # Request 50, should get clamped to 10
        result = await search_web("test", max_results=50)
        assert result.count("Title") == 10

    @pytest.mark.asyncio
    async def test_zero_max_results_clamped_to_one(self, monkeypatch):
        """max_results=0 is clamped to 1."""

        async def fake_http_get(url: str, **kwargs):
            return (
                '<a class="result__a" href="/l/?uddg=https%3A%2F%2Fsite.com">'
                '<b>Title</b></a>'
                '<a class="result__url" href="/l/?uddg=https%3A%2F%2Fsite.com">'
                'site.com</a>'
                '<a class="result__snippet">Snippet.</a>'
            )

        monkeypatch.setattr(
            _search_web_module, "http_get", fake_http_get
        )
        result = await search_web("test", max_results=0)
        assert result.count("Title") == 1

    @pytest.mark.asyncio
    async def test_http_get_failure(self, monkeypatch):
        """Exception from http_get is surfaced gracefully."""

        async def fake_http_get(url: str, **kwargs):
            raise RuntimeError("network down")

        monkeypatch.setattr(
            _search_web_module, "http_get", fake_http_get
        )
        result = await search_web("test query")
        assert result.startswith("Search failed:")
        assert "network down" in result

    @pytest.mark.asyncio
    async def test_strips_html_from_title_and_snippet(self, monkeypatch):
        """HTML in title/snippet is stripped before display."""

        async def fake_http_get(url: str, **kwargs):
            return (
                '<a class="result__a" href="/l/?uddg=https%3A%2F%2Fsite.com">'
                '<b>Bold <i>Title</i></b></a>'
                '<a class="result__url" href="/l/?uddg=https%3A%2F%2Fsite.com">'
                'site.com</a>'
                '<a class="result__snippet">A <span>snippet</span> here.</a>'
            )

        monkeypatch.setattr(
            _search_web_module, "http_get", fake_http_get
        )
        result = await search_web("test query")
        assert "<b>" not in result
        assert "<i>" not in result
        assert "<span>" not in result
        assert "Bold Title" in result
        assert "A snippet here." in result

    @pytest.mark.asyncio
    async def test_url_encoding_in_redirect(self, monkeypatch):
        """uddg redirect URLs are properly decoded."""

        async def fake_http_get(url: str, **kwargs):
            return (
                '<a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com%2Fpath">'
                '<b>Title</b></a>'
                '<a class="result__url" href="/l/?uddg=https%3A%2F%2Fexample.com%2Fpath">'
                'example.com</a>'
                '<a class="result__snippet">Snippet.</a>'
            )

        monkeypatch.setattr(
            _search_web_module, "http_get", fake_http_get
        )
        result = await search_web("test query")
        assert "https://example.com/path" in result
