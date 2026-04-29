"""Tests for failure tracking system (§4)."""

import json
import uuid
from datetime import datetime

import pytest

from hestia.errors import (
    ContextTooLargeError,
    EmptyResponseError,
    FailureClass,
    IllegalTransitionError,
    InferenceServerError,
    InferenceTimeoutError,
    MaxIterationsError,
    PersistenceError,
    ToolExecutionError,
    classify_error,
)
from hestia.persistence.db import Database
from hestia.persistence.failure_store import FailureBundle, FailureStore


class TestClassifyError:
    """Tests for classify_error function."""

    def test_classify_context_too_large(self):
        """ContextTooLargeError maps to CONTEXT_OVERFLOW."""
        exc = ContextTooLargeError("Context is too large")
        fc, severity = classify_error(exc)
        assert fc == FailureClass.CONTEXT_OVERFLOW
        assert severity == "medium"

    def test_classify_empty_response(self):
        """EmptyResponseError maps to EMPTY_RESPONSE."""
        exc = EmptyResponseError("No content")
        fc, severity = classify_error(exc)
        assert fc == FailureClass.EMPTY_RESPONSE
        assert severity == "low"

    def test_classify_inference_timeout(self):
        """InferenceTimeoutError maps to INFERENCE_TIMEOUT."""
        exc = InferenceTimeoutError("Timeout")
        fc, severity = classify_error(exc)
        assert fc == FailureClass.INFERENCE_TIMEOUT
        assert severity == "medium"

    def test_classify_inference_server_error(self):
        """InferenceServerError maps to INFERENCE_ERROR."""
        exc = InferenceServerError("Server error")
        fc, severity = classify_error(exc)
        assert fc == FailureClass.INFERENCE_ERROR
        assert severity == "high"

    def test_classify_persistence_error(self):
        """PersistenceError maps to PERSISTENCE_ERROR."""
        exc = PersistenceError("DB error")
        fc, severity = classify_error(exc)
        assert fc == FailureClass.PERSISTENCE_ERROR
        assert severity == "high"

    def test_classify_illegal_transition(self):
        """IllegalTransitionError maps to ILLEGAL_TRANSITION."""
        exc = IllegalTransitionError("Bad transition")
        fc, severity = classify_error(exc)
        assert fc == FailureClass.ILLEGAL_TRANSITION
        assert severity == "high"

    def test_classify_max_iterations(self):
        """MaxIterationsError maps to MAX_ITERATIONS."""
        exc = MaxIterationsError(10, 10)
        fc, severity = classify_error(exc)
        assert fc == FailureClass.MAX_ITERATIONS
        assert severity == "medium"

    def test_classify_tool_execution_error(self):
        """ToolExecutionError maps to TOOL_ERROR."""
        exc = ToolExecutionError("test_tool", ValueError("boom"))
        fc, severity = classify_error(exc)
        assert fc == FailureClass.TOOL_ERROR
        assert severity == "medium"

    def test_classify_unknown(self):
        """Unknown errors map to UNKNOWN."""
        exc = ValueError("Some random error")
        fc, severity = classify_error(exc)
        assert fc == FailureClass.UNKNOWN
        assert severity == "medium"


class TestFailureStore:
    """Tests for FailureStore persistence."""

    @pytest.fixture
    async def failure_store(self, tmp_path):
        """Create a FailureStore with a fresh database."""
        db_path = tmp_path / "test.db"
        db = Database(f"sqlite+aiosqlite:///{db_path}")
        store = FailureStore(db)
        await db.connect()
        await store.create_table()
        yield store
        await db.close()

    @pytest.mark.asyncio
    async def test_record_and_list(self, failure_store):
        """Record a failure bundle and list it."""
        bundle = FailureBundle(
            id=str(uuid.uuid4()),
            session_id="session_1",
            turn_id="turn_1",
            failure_class=FailureClass.TOOL_ERROR.value,
            severity="medium",
            error_message="Tool failed",
            tool_chain=json.dumps(["tool1", "tool2"]),
            created_at=datetime.now(),
        )

        await failure_store.record(bundle)

        recent = await failure_store.list_recent(limit=10)
        assert len(recent) == 1
        assert recent[0].session_id == "session_1"
        assert recent[0].failure_class == FailureClass.TOOL_ERROR.value

    @pytest.mark.asyncio
    async def test_list_recent_ordering(self, failure_store):
        """List returns bundles ordered by created_at descending."""
        for i in range(3):
            bundle = FailureBundle(
                id=str(uuid.uuid4()),
                session_id=f"session_{i}",
                turn_id=f"turn_{i}",
                failure_class=FailureClass.TOOL_ERROR.value,
                severity="low",
                error_message=f"Error {i}",
                tool_chain="[]",
                created_at=datetime.now(),
            )
            await failure_store.record(bundle)

        recent = await failure_store.list_recent(limit=2)
        assert len(recent) == 2
        # Most recent first
        assert recent[0].session_id == "session_2"
        assert recent[1].session_id == "session_1"

    @pytest.mark.asyncio
    async def test_list_recent_filters_by_class(self, failure_store):
        """list_recent with failure_class filter returns only matching rows."""
        # Create bundles with different classes
        for fc in [FailureClass.TOOL_ERROR, FailureClass.TOOL_ERROR, FailureClass.INFERENCE_ERROR]:
            bundle = FailureBundle(
                id=str(uuid.uuid4()),
                session_id="s1",
                turn_id="t1",
                failure_class=fc.value,
                severity="medium",
                error_message="Error",
                tool_chain="[]",
                created_at=datetime.now(),
            )
            await failure_store.record(bundle)

        # Query with limit=2 but filter for the rare class - should get it
        recent = await failure_store.list_recent(
            limit=2, failure_class=FailureClass.INFERENCE_ERROR.value
        )
        assert len(recent) == 1
        assert recent[0].failure_class == FailureClass.INFERENCE_ERROR.value

    @pytest.mark.asyncio
    async def test_count_by_class(self, failure_store):
        """Count failures grouped by class."""
        # Create bundles of different classes
        for fc in [FailureClass.TOOL_ERROR, FailureClass.TOOL_ERROR, FailureClass.INFERENCE_ERROR]:
            bundle = FailureBundle(
                id=str(uuid.uuid4()),
                session_id="s1",
                turn_id="t1",
                failure_class=fc.value,
                severity="medium",
                error_message="Error",
                tool_chain="[]",
                created_at=datetime.now(),
            )
            await failure_store.record(bundle)

        counts = await failure_store.count_by_class()
        assert counts[FailureClass.TOOL_ERROR.value] == 2
        assert counts[FailureClass.INFERENCE_ERROR.value] == 1
