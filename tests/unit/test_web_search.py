"""Unit tests for web_search tool."""

import httpx
import pytest
import respx

from hestia.config import WebSearchConfig
from hestia.tools.builtin.web_search import make_web_search_tool


class TestMakeWebSearchTool:
    """Tests for web_search tool factory."""

    def test_unconfigured_returns_none(self):
        """Empty config returns None — caller should not register."""
        assert make_web_search_tool(WebSearchConfig()) is None

    def test_missing_api_key_returns_none(self):
        """Provider set but no API key returns None."""
        cfg = WebSearchConfig(provider="tavily", api_key="")
        assert make_web_search_tool(cfg) is None

    def test_unsupported_provider_raises(self):
        """Unsupported provider raises ValueError."""
        cfg = WebSearchConfig(provider="unsupported", api_key="k")
        with pytest.raises(ValueError, match="Unsupported web_search provider"):
            make_web_search_tool(cfg)

    def test_tavily_returns_callable(self):
        """Tavily config returns a callable tool."""
        cfg = WebSearchConfig(provider="tavily", api_key="test-key")
        tool = make_web_search_tool(cfg)
        assert tool is not None
        assert callable(tool)


class TestWebSearchTavily:
    """Tests for Tavily web_search execution."""

    @pytest.fixture
    def tool(self):
        cfg = WebSearchConfig(
            provider="tavily",
            api_key="test-key",
            max_results=3,
        )
        return make_web_search_tool(cfg)

    @pytest.mark.asyncio
    @respx.mock
    async def test_successful_search(self, tool):
        """Mock Tavily response returns formatted results."""
        route = respx.post("https://api.tavily.com/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "title": "First Result",
                            "url": "https://example.com/1",
                            "content": "This is the first result content.",
                        },
                        {
                            "title": "Second Result",
                            "url": "https://example.com/2",
                            "content": "This is the second result content.",
                        },
                    ]
                },
            )
        )

        result = await tool(query="test query")
        assert "First Result" in result
        assert "https://example.com/1" in result
        assert "Second Result" in result
        assert route.called

    @pytest.mark.asyncio
    @respx.mock
    async def test_empty_results(self, tool):
        """Empty results list returns 'No results.'"""
        respx.post("https://api.tavily.com/search").mock(
            return_value=httpx.Response(200, json={"results": []})
        )

        result = await tool(query="nothing")
        assert result == "No results."

    @pytest.mark.asyncio
    @respx.mock
    async def test_http_error(self, tool):
        """HTTP 401 returns a user-friendly error string."""
        respx.post("https://api.tavily.com/search").mock(
            return_value=httpx.Response(401, text="Unauthorized")
        )

        result = await tool(query="test")
        assert result.startswith("Web search failed:")

    @pytest.mark.asyncio
    @respx.mock
    async def test_network_error(self, tool):
        """Network-level error returns a user-friendly error string."""
        respx.post("https://api.tavily.com/search").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = await tool(query="test")
        assert result.startswith("Web search transport error:")

    @pytest.mark.asyncio
    @respx.mock
    async def test_result_truncation(self, tool):
        """Long snippets are truncated to 500 chars."""
        long_content = "A" * 600
        respx.post("https://api.tavily.com/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Long Snippet",
                            "url": "https://example.com/long",
                            "content": long_content,
                        }
                    ]
                },
            )
        )

        result = await tool(query="test")
        assert "Long Snippet" in result
        assert "..." in result
        assert len(result) < len(long_content) + 100

    @pytest.mark.asyncio
    @respx.mock
    async def test_custom_max_results(self, tool):
        """max_results parameter overrides config default."""
        route = respx.post("https://api.tavily.com/search").mock(
            return_value=httpx.Response(200, json={"results": []})
        )

        await tool(query="test", max_results=10)
        request_json = route.calls[0].request.content
        import json

        payload = json.loads(request_json)
        assert payload["max_results"] == 10

    @pytest.mark.asyncio
    @respx.mock
    async def test_time_range_parameter(self, tool):
        """time_range parameter is passed to Tavily."""
        route = respx.post("https://api.tavily.com/search").mock(
            return_value=httpx.Response(200, json={"results": []})
        )

        await tool(query="test", time_range="week")
        request_json = route.calls[0].request.content
        import json

        payload = json.loads(request_json)
        assert payload["time_range"] == "week"
