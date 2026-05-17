"""Unit tests for Bing search_web tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from hestia.tools.builtin.search_web import (
    _decode_bing_redirect,
    _strip_tags,
    _unescape,
    search_web,
)


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


class TestDecodeBingRedirect:
    """Tests for Bing redirect decoding."""

    def test_decodes_base64_redirect(self):
        """Bing's base64-encoded redirect is decoded."""
        # a1 + base64("https://example.com")
        encoded = "a1aHR0cHM6Ly9leGFtcGxlLmNvbQ=="
        url = f"https://www.bing.com/ck/a?u={encoded}&ref"
        result = _decode_bing_redirect(url)
        assert result == "https://example.com"

    def test_returns_original_on_failure(self):
        """Malformed redirects return the original URL."""
        url = "https://www.bing.com/ck/a?u=bad&ref"
        result = _decode_bing_redirect(url)
        assert result == url


class TestSearchWebLogic:
    """Tests for search_web result-processing logic."""

    @pytest.mark.asyncio
    async def test_empty_results_page(self):
        """HTML with no result blocks returns 'No results found.'"""
        mock_response = AsyncMock()
        mock_response.text = "<html><body>No results</body></html>"

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = AsyncMock(return_value=mock_response)

        with patch(
            "hestia.tools.builtin.search_web.AsyncSession",
            return_value=mock_session,
        ):
            result = await search_web("test query")
            assert result == "No results found."

    @pytest.mark.asyncio
    async def test_filters_video_results(self):
        """Video results are skipped."""
        mock_response = AsyncMock()
        mock_response.text = (
            '<h2><a href="/l/?rut=https%3A%2F%2Fexample.com">'
            '<b>Example Title</b></a></h2>'
            '<h2><a href="/l/?rut=https%3A%2F%2Fvideo.com">'
            '<b>Cool Video</b></a></h2>'
        )

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = AsyncMock(return_value=mock_response)

        with patch(
            "hestia.tools.builtin.search_web.AsyncSession",
            return_value=mock_session,
        ):
            result = await search_web("test query")
            assert "Cool Video" not in result
            assert "Example Title" in result

    @pytest.mark.asyncio
    async def test_deduplicates_urls(self):
        """Duplicate URLs only appear once."""
        block = (
            '<h2><a href="/l/?rut=https%3A%2F%2Fdup.com">'
            '<b>Title</b></a></h2>'
        )
        mock_response = AsyncMock()
        mock_response.text = block + block

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = AsyncMock(return_value=mock_response)

        with patch(
            "hestia.tools.builtin.search_web.AsyncSession",
            return_value=mock_session,
        ):
            result = await search_web("test query")
            assert result.count("Title") == 1

    @pytest.mark.asyncio
    async def test_max_results_clamping(self):
        """max_results is clamped to 1-10."""
        blocks = []
        for i in range(15):
            blocks.append(
                f'<h2><a href="/l/?rut=https%3A%2F%2Fsite{i}.com">'
                f'<b>Title {i}</b></a></h2>'
            )
        mock_response = AsyncMock()
        mock_response.text = "".join(blocks)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = AsyncMock(return_value=mock_response)

        with patch(
            "hestia.tools.builtin.search_web.AsyncSession",
            return_value=mock_session,
        ):
            # Request 50, should get clamped to 10
            result = await search_web("test", max_results=50)
            assert result.count("Title") == 10

    @pytest.mark.asyncio
    async def test_zero_max_results_clamped_to_one(self):
        """max_results=0 is clamped to 1."""
        mock_response = AsyncMock()
        mock_response.text = (
            '<h2><a href="/l/?rut=https%3A%2F%2Fsite.com">'
            '<b>Title</b></a></h2>'
        )

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = AsyncMock(return_value=mock_response)

        with patch(
            "hestia.tools.builtin.search_web.AsyncSession",
            return_value=mock_session,
        ):
            result = await search_web("test", max_results=0)
            assert result.count("Title") == 1

    @pytest.mark.asyncio
    async def test_http_get_failure(self):
        """Exception from http_get is surfaced gracefully."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = AsyncMock(side_effect=RuntimeError("network down"))

        with patch(
            "hestia.tools.builtin.search_web.AsyncSession",
            return_value=mock_session,
        ):
            result = await search_web("test query")
            assert result.startswith("Search failed:")
            assert "network down" in result

    @pytest.mark.asyncio
    async def test_strips_html_from_title(self):
        """HTML in title is stripped before display."""
        mock_response = AsyncMock()
        mock_response.text = (
            '<h2><a href="/l/?rut=https%3A%2F%2Fsite.com">'
            '<b>Bold <i>Title</i></b></a></h2>'
        )

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = AsyncMock(return_value=mock_response)

        with patch(
            "hestia.tools.builtin.search_web.AsyncSession",
            return_value=mock_session,
        ):
            result = await search_web("test query")
            assert "<b>" not in result
            assert "<i>" not in result
            assert "Bold Title" in result
