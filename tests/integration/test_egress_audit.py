"""Integration tests for egress audit logging."""

import httpx
import pytest
import respx
from hestia.config import WebSearchConfig
from hestia.persistence.db import Database
from hestia.persistence.trace_store import TraceStore
from hestia.runtime_context import current_session_id, current_trace_store
from hestia.tools.builtin.http_get import http_get
from hestia.tools.builtin.web_search import make_web_search_tool


@pytest.fixture
async def trace_store():
    db = Database("sqlite+aiosqlite:///:memory:")
    await db.connect()
    await db.create_tables()
    store = TraceStore(db)
    await store.create_table()
    yield store
    await db.close()


class TestHttpGetEgress:
    @pytest.mark.asyncio
    @respx.mock
    async def test_records_successful_get(self, trace_store):
        route = respx.get("https://example.com/page").mock(
            return_value=httpx.Response(200, text="ok")
        )

        session_id = "sess-123"
        token_store = current_trace_store.set(trace_store)
        token_session = current_session_id.set(session_id)
        try:
            result = await http_get("https://example.com/page")
        finally:
            current_session_id.reset(token_session)
            current_trace_store.reset(token_store)

        assert result == "ok"
        assert route.called

        rows = await trace_store.egress_summary()
        assert len(rows) == 1
        assert rows[0]["domain"] == "example.com"
        assert rows[0]["total_requests"] == 1
        assert rows[0]["failure_count"] == 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_records_failed_get(self, trace_store):
        respx.get("https://example.com/fail").mock(
            return_value=httpx.Response(500, text="error")
        )

        session_id = "sess-456"
        token_store = current_trace_store.set(trace_store)
        token_session = current_session_id.set(session_id)
        try:
            with pytest.raises(httpx.HTTPStatusError):
                await http_get("https://example.com/fail")
        finally:
            current_session_id.reset(token_session)
            current_trace_store.reset(token_store)

        rows = await trace_store.egress_summary()
        assert len(rows) == 1
        assert rows[0]["total_requests"] == 1
        assert rows[0]["failure_count"] == 1


class TestWebSearchEgress:
    @pytest.mark.asyncio
    @respx.mock
    async def test_records_search_request(self, trace_store):
        route = respx.post("https://api.tavily.com/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {"title": "Test", "url": "https://example.com", "content": "hello"}
                    ]
                },
            )
        )

        cfg = WebSearchConfig(provider="tavily", api_key="test-key")
        tool = make_web_search_tool(cfg)
        assert tool is not None

        session_id = "sess-789"
        token_store = current_trace_store.set(trace_store)
        token_session = current_session_id.set(session_id)
        try:
            result = await tool(query="test")
        finally:
            current_session_id.reset(token_session)
            current_trace_store.reset(token_store)

        assert "Test" in result
        assert route.called

        rows = await trace_store.egress_summary()
        assert len(rows) == 1
        assert rows[0]["domain"] == "api.tavily.com"
        assert rows[0]["total_requests"] == 1
        assert rows[0]["failure_count"] == 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_records_search_failure(self, trace_store):
        respx.post("https://api.tavily.com/search").mock(
            return_value=httpx.Response(401, text="unauthorized")
        )

        cfg = WebSearchConfig(provider="tavily", api_key="test-key")
        tool = make_web_search_tool(cfg)
        assert tool is not None

        session_id = "sess-abc"
        token_store = current_trace_store.set(trace_store)
        token_session = current_session_id.set(session_id)
        try:
            result = await tool(query="test")
        finally:
            current_session_id.reset(token_session)
            current_trace_store.reset(token_store)

        assert "Web search failed:" in result

        rows = await trace_store.egress_summary()
        assert len(rows) == 1
        assert rows[0]["domain"] == "api.tavily.com"
        assert rows[0]["total_requests"] == 1
        assert rows[0]["failure_count"] == 1
