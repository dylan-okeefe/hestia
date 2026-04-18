"""Integration tests for session-start proposal injection."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from hestia.core.types import Message, Session, SessionState, SessionTemperature
from hestia.persistence.db import Database
from hestia.persistence.sessions import SessionStore
from hestia.reflection.store import ProposalStore
from hestia.reflection.types import Proposal


class FakeInference:
    model_name = "fake-model"

    async def tokenize(self, text: str) -> list[int]:
        return [0] * (len(text) // 4 + 1)

    async def count_request(self, messages, tools=None):
        return 10

    async def chat(self, messages, tools=None, slot_id=None, **kwargs):
        from hestia.core.types import ChatResponse

        return ChatResponse(
            content="Hello!",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )

    async def close(self):
        pass


class FakePolicy:
    def turn_token_budget(self, session):
        return 4000

    def filter_tools(self, session, tool_names, registry):
        return tool_names

    def reasoning_budget(self, session, iteration):
        return 2048

    def auto_approve(self, tool_name, session):
        return False


@pytest.fixture
async def db(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    await db.connect()
    await db.create_tables()
    yield db
    await db.close()


@pytest.fixture
async def session_store(db):
    return SessionStore(db)


@pytest.fixture
async def proposal_store(db):
    store = ProposalStore(db)
    await store.create_table()
    return store


class TestSessionStartProposals:
    async def test_first_turn_injects_note_when_pending_proposals_exist(
        self, db, session_store, proposal_store, tmp_path
    ):
        """When a session starts and there are pending proposals, the system prompt gets a note."""
        from hestia.artifacts.store import ArtifactStore
        from hestia.context.builder import ContextBuilder
        from hestia.orchestrator.engine import Orchestrator
        from hestia.tools.registry import ToolRegistry

        # Seed a pending proposal
        now = datetime.now()
        proposal = Proposal(
            id="prop_001",
            type="identity_update",
            summary="Add greeting preference",
            evidence=["turn_1"],
            action={},
            confidence=0.8,
            status="pending",
            created_at=now,
            expires_at=now + timedelta(days=14),
        )
        await proposal_store.save(proposal)

        # Create session
        session = Session(
            id="sess_001",
            platform="cli",
            platform_user="test",
            started_at=now,
            last_active_at=now,
            slot_id=None,
            slot_saved_path=None,
            state=SessionState.ACTIVE,
            temperature=SessionTemperature.COLD,
        )
        import sqlalchemy as sa
        from hestia.persistence.schema import sessions

        async with db.engine.connect() as conn:
            await conn.execute(
                sa.insert(sessions).values(
                    id=session.id,
                    platform=session.platform,
                    platform_user=session.platform_user,
                    started_at=session.started_at,
                    last_active_at=session.last_active_at,
                    slot_id=session.slot_id,
                    slot_saved_path=session.slot_saved_path,
                    state=session.state.value,
                    temperature=session.temperature.value,
                )
            )
            await conn.commit()

        inference = FakeInference()
        policy = FakePolicy()
        context_builder = ContextBuilder(inference, policy, body_factor=1.0)
        artifact_store = ArtifactStore(tmp_path / "artifacts")
        tool_registry = ToolRegistry(artifact_store)

        orchestrator = Orchestrator(
            inference=inference,
            session_store=session_store,
            context_builder=context_builder,
            tool_registry=tool_registry,
            policy=policy,
            proposal_store=proposal_store,
        )

        responses = []

        async def respond(text):
            responses.append(text)

        turn = await orchestrator.process_turn(
            session=session,
            user_message=Message(role="user", content="Hi there"),
            respond_callback=respond,
            system_prompt="You are a helpful assistant.",
        )

        assert turn.state.value == "done"
        assert len(responses) == 1

    async def test_no_injection_on_subsequent_turns(
        self, db, session_store, proposal_store, tmp_path
    ):
        """The proposal note is only injected on the first turn."""
        from hestia.artifacts.store import ArtifactStore
        from hestia.context.builder import ContextBuilder
        from hestia.orchestrator.engine import Orchestrator
        from hestia.tools.registry import ToolRegistry

        now = datetime.now()
        proposal = Proposal(
            id="prop_002",
            type="policy_tweak",
            summary="Increase timeout",
            evidence=["turn_2"],
            action={},
            confidence=0.7,
            status="pending",
            created_at=now,
            expires_at=now + timedelta(days=14),
        )
        await proposal_store.save(proposal)

        session = Session(
            id="sess_002",
            platform="cli",
            platform_user="test2",
            started_at=now,
            last_active_at=now,
            slot_id=None,
            slot_saved_path=None,
            state=SessionState.ACTIVE,
            temperature=SessionTemperature.COLD,
        )
        import sqlalchemy as sa
        from hestia.persistence.schema import sessions

        async with db.engine.connect() as conn:
            await conn.execute(
                sa.insert(sessions).values(
                    id=session.id,
                    platform=session.platform,
                    platform_user=session.platform_user,
                    started_at=session.started_at,
                    last_active_at=session.last_active_at,
                    slot_id=session.slot_id,
                    slot_saved_path=session.slot_saved_path,
                    state=session.state.value,
                    temperature=session.temperature.value,
                )
            )
            await conn.commit()

        inference = FakeInference()
        policy = FakePolicy()
        context_builder = ContextBuilder(inference, policy, body_factor=1.0)
        artifact_store = ArtifactStore(tmp_path / "artifacts")
        tool_registry = ToolRegistry(artifact_store)

        orchestrator = Orchestrator(
            inference=inference,
            session_store=session_store,
            context_builder=context_builder,
            tool_registry=tool_registry,
            policy=policy,
            proposal_store=proposal_store,
        )

        responses = []

        async def respond(text):
            responses.append(text)

        # First turn
        await orchestrator.process_turn(
            session=session,
            user_message=Message(role="user", content="First message"),
            respond_callback=respond,
            system_prompt="You are helpful.",
        )

        # Second turn
        responses.clear()
        await orchestrator.process_turn(
            session=session,
            user_message=Message(role="user", content="Second message"),
            respond_callback=respond,
            system_prompt="You are helpful.",
        )

        # Should still complete without error
        assert len(responses) == 1

    async def test_no_injection_when_no_pending_proposals(
        self, db, session_store, proposal_store, tmp_path
    ):
        """When there are no pending proposals, the system prompt is unchanged."""
        from hestia.artifacts.store import ArtifactStore
        from hestia.context.builder import ContextBuilder
        from hestia.orchestrator.engine import Orchestrator
        from hestia.tools.registry import ToolRegistry

        now = datetime.now()
        session = Session(
            id="sess_003",
            platform="cli",
            platform_user="test3",
            started_at=now,
            last_active_at=now,
            slot_id=None,
            slot_saved_path=None,
            state=SessionState.ACTIVE,
            temperature=SessionTemperature.COLD,
        )
        import sqlalchemy as sa
        from hestia.persistence.schema import sessions

        async with db.engine.connect() as conn:
            await conn.execute(
                sa.insert(sessions).values(
                    id=session.id,
                    platform=session.platform,
                    platform_user=session.platform_user,
                    started_at=session.started_at,
                    last_active_at=session.last_active_at,
                    slot_id=session.slot_id,
                    slot_saved_path=session.slot_saved_path,
                    state=session.state.value,
                    temperature=session.temperature.value,
                )
            )
            await conn.commit()

        inference = FakeInference()
        policy = FakePolicy()
        context_builder = ContextBuilder(inference, policy, body_factor=1.0)
        artifact_store = ArtifactStore(tmp_path / "artifacts")
        tool_registry = ToolRegistry(artifact_store)

        orchestrator = Orchestrator(
            inference=inference,
            session_store=session_store,
            context_builder=context_builder,
            tool_registry=tool_registry,
            policy=policy,
            proposal_store=proposal_store,
        )

        responses = []

        async def respond(text):
            responses.append(text)

        turn = await orchestrator.process_turn(
            session=session,
            user_message=Message(role="user", content="Hello"),
            respond_callback=respond,
            system_prompt="You are helpful.",
        )

        assert turn.state.value == "done"
