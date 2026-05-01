"""Unit tests for proposal tools."""

from __future__ import annotations

import pytest

from hestia.persistence.db import Database
from hestia.reflection.store import ProposalStore
from hestia.reflection.types import Proposal
from hestia.tools.builtin.proposal_tools import (
    make_accept_proposal_tool,
    make_defer_proposal_tool,
    make_list_proposals_tool,
    make_reject_proposal_tool,
    make_show_proposal_tool,
)


class TestProposalTools:
    @pytest.fixture
    async def tools(self, tmp_path):
        """Create proposal tools bound to a fresh ProposalStore."""
        db = Database(f"sqlite+aiosqlite:///{tmp_path}/test.db")
        await db.connect()
        await db.create_tables()
        store = ProposalStore(db)
        await store.create_table()

        list_tool = make_list_proposals_tool(store)
        show_tool = make_show_proposal_tool(store)
        accept_tool = make_accept_proposal_tool(store)
        reject_tool = make_reject_proposal_tool(store)
        defer_tool = make_defer_proposal_tool(store)

        yield store, list_tool, show_tool, accept_tool, reject_tool, defer_tool
        await db.close()

    @pytest.fixture
    async def sample_proposal(self, tools):
        """Create a sample proposal in the store."""
        from datetime import timedelta

        from hestia.core.clock import utcnow

        store = tools[0]
        now = utcnow()
        proposal = Proposal(
            id="prop_001",
            type="identity_update",
            summary="Add greeting preference",
            evidence=["turn_1"],
            action={"file": "SOUL.md", "append": "- Greeting: casual"},
            confidence=0.9,
            status="pending",
            created_at=now,
            expires_at=now + timedelta(days=14),
        )
        await store.save(proposal)
        return proposal

    @pytest.mark.asyncio
    async def test_list_proposals_returns_formatted(self, tools, sample_proposal):
        """list_proposals returns formatted results."""
        _, list_tool, _, _, _, _ = tools
        result = await list_tool("pending")
        assert "prop_001" in result
        assert "identity_update" in result
        assert "Add greeting preference" in result

    @pytest.mark.asyncio
    async def test_list_proposals_empty(self, tools):
        """list_proposals returns helpful message when empty."""
        _, list_tool, _, _, _, _ = tools
        result = await list_tool("accepted")
        assert "No accepted proposals found" in result

    @pytest.mark.asyncio
    async def test_list_proposals_invalid_status(self, tools):
        """list_proposals rejects invalid status."""
        _, list_tool, _, _, _, _ = tools
        result = await list_tool("invalid")
        assert "Invalid status" in result

    @pytest.mark.asyncio
    async def test_show_proposal_details(self, tools, sample_proposal):
        """show_proposal returns full details."""
        _, _, show_tool, _, _, _ = tools
        result = await show_tool("prop_001")
        assert "prop_001" in result
        assert "identity_update" in result
        assert "Add greeting preference" in result
        assert "0.9" in result
        assert "pending" in result

    @pytest.mark.asyncio
    async def test_show_proposal_not_found(self, tools):
        """show_proposal returns friendly message for unknown id."""
        _, _, show_tool, _, _, _ = tools
        result = await show_tool("nonexistent")
        assert "No proposal with id nonexistent" in result

    @pytest.mark.asyncio
    async def test_accept_proposal(self, tools, sample_proposal):
        """accept_proposal updates status to accepted."""
        _, _, _, accept_tool, _, _ = tools
        result = await accept_tool("prop_001", note="Looks good")
        assert "Accepted proposal prop_001" in result

        store = tools[0]
        fetched = await store.get("prop_001")
        assert fetched is not None
        assert fetched.status == "accepted"
        assert fetched.review_note == "Looks good"

    @pytest.mark.asyncio
    async def test_accept_proposal_not_found(self, tools):
        """accept_proposal returns error for unknown id."""
        _, _, _, accept_tool, _, _ = tools
        result = await accept_tool("nonexistent")
        assert "No proposal with id nonexistent" in result

    @pytest.mark.asyncio
    async def test_reject_proposal(self, tools, sample_proposal):
        """reject_proposal updates status to rejected."""
        _, _, _, _, reject_tool, _ = tools
        result = await reject_tool("prop_001", note="Not now")
        assert "Rejected proposal prop_001" in result

        store = tools[0]
        fetched = await store.get("prop_001")
        assert fetched is not None
        assert fetched.status == "rejected"
        assert fetched.review_note == "Not now"

    @pytest.mark.asyncio
    async def test_reject_proposal_not_found(self, tools):
        """reject_proposal returns error for unknown id."""
        _, _, _, _, reject_tool, _ = tools
        result = await reject_tool("nonexistent")
        assert "No proposal with id nonexistent" in result

    @pytest.mark.asyncio
    async def test_defer_proposal(self, tools, sample_proposal):
        """defer_proposal updates status to deferred."""
        _, _, _, _, _, defer_tool = tools
        result = await defer_tool("prop_001")
        assert "Deferred proposal prop_001" in result

        store = tools[0]
        fetched = await store.get("prop_001")
        assert fetched is not None
        assert fetched.status == "deferred"

    @pytest.mark.asyncio
    async def test_defer_proposal_not_found(self, tools):
        """defer_proposal returns error for unknown id."""
        _, _, _, _, _, defer_tool = tools
        result = await defer_tool("nonexistent")
        assert "No proposal with id nonexistent" in result

    @pytest.mark.asyncio
    async def test_accept_requires_confirmation(self, tools):
        """accept_proposal requires confirmation."""
        _, _, _, accept_tool, _, _ = tools
        assert hasattr(accept_tool, "__hestia_tool__")
        assert accept_tool.__hestia_tool__.requires_confirmation is True

    @pytest.mark.asyncio
    async def test_reject_does_not_require_confirmation(self, tools):
        """reject_proposal does not require confirmation."""
        _, _, _, _, reject_tool, _ = tools
        assert hasattr(reject_tool, "__hestia_tool__")
        assert reject_tool.__hestia_tool__.requires_confirmation is False

    @pytest.mark.asyncio
    async def test_defer_does_not_require_confirmation(self, tools):
        """defer_proposal does not require confirmation."""
        _, _, _, _, _, defer_tool = tools
        assert hasattr(defer_tool, "__hestia_tool__")
        assert defer_tool.__hestia_tool__.requires_confirmation is False

    @pytest.mark.asyncio
    async def test_tools_have_self_management_capability(self, tools):
        """All proposal tools have SELF_MANAGEMENT capability."""
        from hestia.tools.capabilities import SELF_MANAGEMENT

        _, list_tool, show_tool, accept_tool, reject_tool, defer_tool = tools
        for tool_func in [list_tool, show_tool, accept_tool, reject_tool, defer_tool]:
            assert hasattr(tool_func, "__hestia_tool__")
            assert SELF_MANAGEMENT in tool_func.__hestia_tool__.capabilities

    @pytest.mark.asyncio
    async def test_list_proposals_filters_by_status(self, tools):
        """list_proposals respects status filter."""
        from datetime import timedelta

        from hestia.core.clock import utcnow

        store, list_tool, _, _, _, _ = tools
        now = utcnow()
        for _i, status in enumerate(["pending", "accepted", "rejected", "deferred"]):
            p = Proposal(
                id=f"prop_{status}",
                type="tool_fix",
                summary=f"Proposal {status}",
                evidence=[],
                action={},
                confidence=0.5,
                status=status,
                created_at=now,
                expires_at=now + timedelta(days=14),
            )
            await store.save(p)

        pending_result = await list_tool("pending")
        assert "prop_pending" in pending_result
        assert "prop_accepted" not in pending_result

        accepted_result = await list_tool("accepted")
        assert "prop_accepted" in accepted_result
        assert "prop_pending" not in accepted_result
