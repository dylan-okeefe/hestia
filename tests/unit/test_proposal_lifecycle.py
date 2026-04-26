"""Unit tests for ProposalStore lifecycle operations."""

from __future__ import annotations

import pytest

from hestia.persistence.db import Database
from hestia.reflection.store import ProposalStore
from hestia.reflection.types import Proposal


class TestProposalLifecycle:
    @pytest.fixture
    async def proposal_store(self, tmp_path):
        db = Database(f"sqlite+aiosqlite:///{tmp_path}/test.db")
        await db.connect()
        await db.create_tables()
        store = ProposalStore(db)
        await store.create_table()
        yield store
        await db.close()

    async def test_create_and_get(self, proposal_store):
        from datetime import timedelta

        from hestia.core.clock import utcnow

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
        await proposal_store.save(proposal)

        fetched = await proposal_store.get("prop_001")
        assert fetched is not None
        assert fetched.id == "prop_001"
        assert fetched.type == "identity_update"
        assert fetched.status == "pending"

    async def test_list_by_status(self, proposal_store):
        from datetime import timedelta

        from hestia.core.clock import utcnow

        now = utcnow()
        for i, status in enumerate(["pending", "pending", "accepted", "rejected"]):
            p = Proposal(
                id=f"prop_{i:03d}",
                type="tool_fix",
                summary=f"Proposal {i}",
                evidence=[],
                action={},
                confidence=0.5,
                status=status,
                created_at=now,
                expires_at=now + timedelta(days=14),
            )
            await proposal_store.save(p)

        pending = await proposal_store.list_by_status(status="pending")
        assert len(pending) == 2

        accepted = await proposal_store.list_by_status(status="accepted")
        assert len(accepted) == 1

    async def test_accept_reject_defer(self, proposal_store):
        from datetime import timedelta

        from hestia.core.clock import utcnow

        now = utcnow()
        p = Proposal(
            id="prop_004",
            type="policy_tweak",
            summary="Increase timeout",
            evidence=["turn_3"],
            action={"config_key": "timeout", "value": 30},
            confidence=0.7,
            status="pending",
            created_at=now,
            expires_at=now + timedelta(days=14),
        )
        await proposal_store.save(p)

        ok = await proposal_store.update_status("prop_004", "accepted", review_note="Looks good")
        assert ok is True

        fetched = await proposal_store.get("prop_004")
        assert fetched is not None
        assert fetched.status == "accepted"
        assert fetched.review_note == "Looks good"
        assert fetched.reviewed_at is not None

    async def test_prune_expired(self, proposal_store):
        from datetime import timedelta

        from hestia.core.clock import utcnow

        now = utcnow()
        # One expired, one not
        p1 = Proposal(
            id="prop_exp",
            type="tool_fix",
            summary="Expired proposal",
            evidence=[],
            action={},
            confidence=0.5,
            status="pending",
            created_at=now - timedelta(days=20),
            expires_at=now - timedelta(days=1),
        )
        p2 = Proposal(
            id="prop_live",
            type="tool_fix",
            summary="Live proposal",
            evidence=[],
            action={},
            confidence=0.5,
            status="pending",
            created_at=now,
            expires_at=now + timedelta(days=14),
        )
        await proposal_store.save(p1)
        await proposal_store.save(p2)

        pruned = await proposal_store.prune_expired(now)
        assert pruned == 1

        fetched = await proposal_store.get("prop_exp")
        assert fetched is not None
        assert fetched.status == "expired"

        fetched2 = await proposal_store.get("prop_live")
        assert fetched2 is not None
        assert fetched2.status == "pending"

    async def test_count_by_status(self, proposal_store):
        from datetime import timedelta

        from hestia.core.clock import utcnow

        now = utcnow()
        for i, status in enumerate(["pending", "pending", "accepted"]):
            p = Proposal(
                id=f"prop_{status}_{i}",
                type="identity_update",
                summary="Test",
                evidence=[],
                action={},
                confidence=0.5,
                status=status,
                created_at=now,
                expires_at=now + timedelta(days=14),
            )
            await proposal_store.save(p)

        counts = await proposal_store.count_by_status()
        assert counts.get("pending", 0) == 2
        assert counts.get("accepted", 0) == 1

    async def test_update_missing_proposal(self, proposal_store):
        ok = await proposal_store.update_status("prop_missing", "accepted")
        assert ok is False
