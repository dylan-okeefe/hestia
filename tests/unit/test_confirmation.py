"""Unit tests for shared confirmation infrastructure."""

from __future__ import annotations

import asyncio

import pytest

from hestia.platforms.confirmation import (
    ConfirmationStore,
    render_args_for_human_review,
)


class TestRenderArgsForHumanReview:
    """Tests for the args-rendering helper."""

    def test_simple_args(self):
        result = render_args_for_human_review("terminal", {"command": "echo hi"})
        assert "command" in result
        assert "echo hi" in result

    def test_truncates_long_fields(self):
        long_value = "x" * 500
        result = render_args_for_human_review("write_file", {"content": long_value})
        assert "..." in result
        assert len(result) < 600  # truncated + JSON overhead

    def test_non_string_values(self):
        result = render_args_for_human_review("test", {"count": 42, "flag": True})
        assert "42" in result
        assert "true" in result


class TestConfirmationStore:
    """Tests for the in-memory confirmation store."""

    @pytest.mark.asyncio
    async def test_create_returns_awaitable_future(self):
        store = ConfirmationStore()
        req = store.create("terminal", {"command": "echo hi"})
        assert req.id
        assert req.tool_name == "terminal"
        assert not req.future.done()
        store.resolve(req.id, True)
        assert await req.future is True

    @pytest.mark.asyncio
    async def test_resolve_approves(self):
        store = ConfirmationStore()
        req = store.create("write_file", {"path": "test.txt"})
        resolved = store.resolve(req.id, True)
        assert resolved is True
        assert await req.future is True

    @pytest.mark.asyncio
    async def test_resolve_denies(self):
        store = ConfirmationStore()
        req = store.create("write_file", {"path": "test.txt"})
        resolved = store.resolve(req.id, False)
        assert resolved is True
        assert await req.future is False

    @pytest.mark.asyncio
    async def test_resolve_unknown_id_returns_false(self):
        store = ConfirmationStore()
        resolved = store.resolve("nonexistent", True)
        assert resolved is False

    @pytest.mark.asyncio
    async def test_cancel_sets_false(self):
        store = ConfirmationStore()
        req = store.create("terminal", {"command": "ls"})
        cancelled = store.cancel(req.id)
        assert cancelled is True
        assert await req.future is False

    @pytest.mark.asyncio
    async def test_gc_removes_expired_requests(self):
        store = ConfirmationStore()
        req = store.create("terminal", {"command": "ls"}, timeout_seconds=0.01)
        await asyncio.sleep(0.05)
        assert store.get(req.id) is None
        # Future should have been resolved to False by GC
        assert await req.future is False

    @pytest.mark.asyncio
    async def test_len_counts_pending(self):
        store = ConfirmationStore()
        req1 = store.create("a", {})
        req2 = store.create("b", {})
        assert len(store) == 2
        store.resolve(req1.id, True)
        assert len(store) == 1
        store.resolve(req2.id, True)
        assert len(store) == 0
