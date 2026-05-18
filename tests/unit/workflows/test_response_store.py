"""Tests for WorkflowResponseStore."""

from __future__ import annotations

import asyncio

import pytest

from hestia.workflows.response_store import WorkflowResponseStore


class TestWorkflowResponseStore:
    @pytest.mark.asyncio
    async def test_create_and_resolve(self) -> None:
        store = WorkflowResponseStore()
        request_id, future = store.create("telegram", "12345")

        assert request_id is not None
        assert len(store) == 1

        resolved = store.resolve(request_id, "Approve")
        assert resolved is True

        result = await future
        assert result == "Approve"
        assert len(store) == 0

    @pytest.mark.asyncio
    async def test_resolve_unknown_request(self) -> None:
        store = WorkflowResponseStore()
        resolved = store.resolve("nonexistent", "yes")
        assert resolved is False

    @pytest.mark.asyncio
    async def test_cancel_request(self) -> None:
        store = WorkflowResponseStore()
        request_id, future = store.create("matrix", "!room:matrix.org")

        cancelled = store.cancel(request_id)
        assert cancelled is True

        with pytest.raises(asyncio.CancelledError):
            await future

    @pytest.mark.asyncio
    async def test_find_pending(self) -> None:
        store = WorkflowResponseStore()
        request_id, _ = store.create("telegram", "12345")

        found = store.find_pending("telegram", "12345")
        assert found == request_id

        not_found = store.find_pending("telegram", "99999")
        assert not_found is None

    @pytest.mark.asyncio
    async def test_multiple_requests(self) -> None:
        store = WorkflowResponseStore()
        req1, fut1 = store.create("telegram", "123")
        req2, fut2 = store.create("matrix", "!room:matrix.org")

        assert len(store) == 2

        store.resolve(req1, "yes")
        assert (await fut1) == "yes"
        assert len(store) == 1

        store.resolve(req2, "no")
        assert (await fut2) == "no"
        assert len(store) == 0

    @pytest.mark.asyncio
    async def test_sweep_stale_removes_old_requests(self) -> None:
        store = WorkflowResponseStore()
        store.create("telegram", "123", timeout_seconds=0.1)
        assert len(store) == 1

        # Wait for the request to become stale
        await asyncio.sleep(0.25)
        store._do_sweep()
        assert len(store) == 0

        store.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_sweep_task(self) -> None:
        store = WorkflowResponseStore()
        store.create("telegram", "123")
        assert store._sweep_task is not None
        store.stop()
        assert store._sweep_task is None
