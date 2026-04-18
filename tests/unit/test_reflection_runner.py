"""Unit tests for ReflectionRunner."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from hestia.core.types import ChatResponse
from hestia.reflection.runner import ReflectionRunner
from hestia.reflection.store import ProposalStore
from hestia.reflection.types import Proposal


class FakeInferenceClient:
    """Fake inference client that returns canned JSON responses."""

    def __init__(self, responses: list[ChatResponse] | None = None):
        self.model_name = "fake-model"
        self.responses = responses or []
        self.call_count = 0

    async def tokenize(self, text: str) -> list[int]:
        return [0] * (len(text) // 4 + 1)

    async def count_request(self, messages, tools=None):
        return 10

    async def chat(self, messages, tools=None, slot_id=None, **kwargs):
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response
        return ChatResponse(
            content="{}",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )

    async def close(self):
        pass


class FakeTraceStore:
    """Fake trace store with canned traces."""

    def __init__(self, traces=None):
        self.traces = traces or []

    async def list_recent(self, limit=20, outcome=None):
        return self.traces[:limit]


class FakeProposalStore:
    """Fake proposal store that keeps proposals in memory."""

    def __init__(self):
        self.proposals: list[Proposal] = []

    async def create_table(self):
        pass

    async def save(self, proposal: Proposal):
        self.proposals.append(proposal)

    async def list_by_status(self, status=None, limit=100):
        if status:
            return [p for p in self.proposals if p.status == status][:limit]
        return self.proposals[:limit]

    async def pending_count(self):
        return len([p for p in self.proposals if p.status == "pending"])

    async def prune_expired(self):
        return 0


@pytest.fixture
def fake_trace_store():
    from hestia.persistence.trace_store import TraceRecord

    traces = [
        TraceRecord(
            id="t1",
            session_id="s1",
            turn_id="turn_1",
            started_at=datetime.now(),
            ended_at=datetime.now(),
            user_input_summary="Set timer for 5 minutes",
            tools_called=["current_time"],
            tool_call_count=1,
            delegated=False,
            outcome="success",
            artifact_handles=[],
            prompt_tokens=10,
            completion_tokens=5,
            reasoning_tokens=0,
            total_duration_ms=1000,
        ),
        TraceRecord(
            id="t2",
            session_id="s1",
            turn_id="turn_2",
            started_at=datetime.now(),
            ended_at=datetime.now(),
            user_input_summary="No, actually 10 minutes",
            tools_called=["current_time"],
            tool_call_count=1,
            delegated=False,
            outcome="success",
            artifact_handles=[],
            prompt_tokens=10,
            completion_tokens=5,
            reasoning_tokens=0,
            total_duration_ms=1000,
        ),
    ]
    return FakeTraceStore(traces)


@pytest.fixture
def fake_proposal_store():
    return FakeProposalStore()


@pytest.fixture
def reflection_config():
    from hestia.config import ReflectionConfig

    return ReflectionConfig(
        enabled=True,
        lookback_turns=10,
        proposals_per_run=5,
        expire_days=7,
    )


class TestReflectionRunner:
    async def test_mines_patterns_and_generates_proposals(
        self,
        fake_trace_store,
        fake_proposal_store,
        reflection_config,
    ):
        observations_json = json.dumps(
            {
                "observations": [
                    {
                        "category": "correction",
                        "turn_id": "turn_2",
                        "description": "User corrected timer duration",
                        "confidence": 0.9,
                    }
                ]
            }
        )
        proposals_json = json.dumps(
            {
                "proposals": [
                    {
                        "type": "identity_update",
                        "summary": "Add preferred timer default to identity",
                        "evidence": ["turn_2"],
                        "action": {"file": "SOUL.md", "append": "- Default timer: 10 min"},
                        "confidence": 0.85,
                    }
                ]
            }
        )

        inference = FakeInferenceClient(
            responses=[
                ChatResponse(
                    content=observations_json,
                    reasoning_content=None,
                    tool_calls=[],
                    finish_reason="stop",
                    prompt_tokens=10,
                    completion_tokens=5,
                    total_tokens=15,
                ),
                ChatResponse(
                    content=proposals_json,
                    reasoning_content=None,
                    tool_calls=[],
                    finish_reason="stop",
                    prompt_tokens=10,
                    completion_tokens=5,
                    total_tokens=15,
                ),
            ]
        )

        runner = ReflectionRunner(
            config=reflection_config,
            inference=inference,
            trace_store=fake_trace_store,
            proposal_store=fake_proposal_store,
        )

        proposals = await runner.run()

        assert len(proposals) == 1
        assert proposals[0].type == "identity_update"
        assert proposals[0].confidence == pytest.approx(0.85)
        assert proposals[0].status == "pending"
        assert proposals[0].evidence == ["turn_2"]

    async def test_no_observations_yields_no_proposals(
        self,
        fake_trace_store,
        fake_proposal_store,
        reflection_config,
    ):
        observations_json = json.dumps({"observations": []})

        inference = FakeInferenceClient(
            responses=[
                ChatResponse(
                    content=observations_json,
                    reasoning_content=None,
                    tool_calls=[],
                    finish_reason="stop",
                    prompt_tokens=10,
                    completion_tokens=5,
                    total_tokens=15,
                ),
            ]
        )

        runner = ReflectionRunner(
            config=reflection_config,
            inference=inference,
            trace_store=fake_trace_store,
            proposal_store=fake_proposal_store,
        )

        proposals = await runner.run()
        assert proposals == []

    async def test_disabled_config_skips_run(
        self,
        fake_trace_store,
        fake_proposal_store,
    ):
        from hestia.config import ReflectionConfig

        disabled_config = ReflectionConfig(enabled=False)
        inference = FakeInferenceClient()

        runner = ReflectionRunner(
            config=disabled_config,
            inference=inference,
            trace_store=fake_trace_store,
            proposal_store=fake_proposal_store,
        )

        proposals = await runner.run()
        assert proposals == []
        assert inference.call_count == 0

    async def test_proposals_capped_at_limit(
        self,
        fake_trace_store,
        fake_proposal_store,
        reflection_config,
    ):
        reflection_config.proposals_per_run = 2

        observations_json = json.dumps(
            {
                "observations": [
                    {
                        "category": "frustration",
                        "turn_id": "turn_1",
                        "description": "User repeated request",
                        "confidence": 0.8,
                    }
                ]
            }
        )
        proposals_json = json.dumps(
            {
                "proposals": [
                    {
                        "type": "policy_tweak",
                        "summary": f"Proposal {i}",
                        "evidence": ["turn_1"],
                        "action": {},
                        "confidence": 0.5 + i * 0.05,
                    }
                    for i in range(5)
                ]
            }
        )

        inference = FakeInferenceClient(
            responses=[
                ChatResponse(
                    content=observations_json,
                    reasoning_content=None,
                    tool_calls=[],
                    finish_reason="stop",
                    prompt_tokens=10,
                    completion_tokens=5,
                    total_tokens=15,
                ),
                ChatResponse(
                    content=proposals_json,
                    reasoning_content=None,
                    tool_calls=[],
                    finish_reason="stop",
                    prompt_tokens=10,
                    completion_tokens=5,
                    total_tokens=15,
                ),
            ]
        )

        runner = ReflectionRunner(
            config=reflection_config,
            inference=inference,
            trace_store=fake_trace_store,
            proposal_store=fake_proposal_store,
        )

        proposals = await runner.run()
        assert len(proposals) == 2

    async def test_extracts_json_from_markdown_block(
        self,
        fake_trace_store,
        fake_proposal_store,
        reflection_config,
    ):
        observations_md = '```json\n{"observations": []}\n```'

        inference = FakeInferenceClient(
            responses=[
                ChatResponse(
                    content=observations_md,
                    reasoning_content=None,
                    tool_calls=[],
                    finish_reason="stop",
                    prompt_tokens=10,
                    completion_tokens=5,
                    total_tokens=15,
                ),
            ]
        )

        runner = ReflectionRunner(
            config=reflection_config,
            inference=inference,
            trace_store=fake_trace_store,
            proposal_store=fake_proposal_store,
        )

        proposals = await runner.run()
        assert proposals == []
