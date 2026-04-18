"""Proposal storage using raw SQLite DDL (consistent with TraceStore pattern)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa

from hestia.core.clock import utcnow
from hestia.reflection.types import Proposal, ProposalStatus

if TYPE_CHECKING:
    from hestia.persistence.db import Database


class ProposalStore:
    """Typed CRUD wrapper for proposal persistence."""

    def __init__(self, db: "Database") -> None:
        self._db = db

    async def create_table(self) -> None:
        """Create the proposals table if it doesn't exist."""
        ddl = """
        CREATE TABLE IF NOT EXISTS proposals (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            summary TEXT NOT NULL,
            evidence TEXT NOT NULL,
            action TEXT NOT NULL,
            confidence REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            reviewed_at TEXT,
            review_note TEXT
        )
        """
        idx_status = "CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status, created_at)"
        idx_expires = "CREATE INDEX IF NOT EXISTS idx_proposals_expires ON proposals(expires_at)"
        idx_type = "CREATE INDEX IF NOT EXISTS idx_proposals_type ON proposals(type)"

        async with self._db.engine.connect() as conn:
            await conn.execute(sa.text(ddl))
            await conn.execute(sa.text(idx_status))
            await conn.execute(sa.text(idx_expires))
            await conn.execute(sa.text(idx_type))
            await conn.commit()

    async def save(self, proposal: Proposal) -> None:
        """Persist a proposal."""
        sql = sa.text(
            "INSERT INTO proposals (id, type, summary, evidence, action, confidence, status, "
            "created_at, expires_at, reviewed_at, review_note) "
            "VALUES (:id, :type, :summary, :evidence, :action, :confidence, :status, "
            ":created_at, :expires_at, :reviewed_at, :review_note)"
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(
                sql,
                {
                    "id": proposal.id,
                    "type": proposal.type,
                    "summary": proposal.summary,
                    "evidence": json.dumps(proposal.evidence),
                    "action": json.dumps(proposal.action),
                    "confidence": proposal.confidence,
                    "status": proposal.status,
                    "created_at": proposal.created_at.isoformat(),
                    "expires_at": proposal.expires_at.isoformat(),
                    "reviewed_at": proposal.reviewed_at.isoformat() if proposal.reviewed_at else None,
                    "review_note": proposal.review_note,
                },
            )
            await conn.commit()

    async def get(self, proposal_id: str) -> Proposal | None:
        """Get a proposal by ID."""
        sql = sa.text("SELECT * FROM proposals WHERE id = :id")
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"id": proposal_id})
            row = result.fetchone()
            if row:
                return self._row_to_proposal(row)
            return None

    async def list_by_status(
        self,
        status: ProposalStatus | None = None,
        limit: int = 100,
    ) -> list[Proposal]:
        """List proposals, optionally filtered by status."""
        if status:
            sql = sa.text(
                "SELECT * FROM proposals WHERE status = :status "
                "ORDER BY created_at DESC LIMIT :limit"
            )
            params = {"status": status, "limit": limit}
        else:
            sql = sa.text("SELECT * FROM proposals ORDER BY created_at DESC LIMIT :limit")
            params = {"limit": limit}

        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, params)
            rows = result.fetchall()
            return [self._row_to_proposal(row) for row in rows]

    async def update_status(
        self,
        proposal_id: str,
        status: ProposalStatus,
        review_note: str | None = None,
    ) -> bool:
        """Update proposal status and optional review note.

        Returns True if the proposal was found and updated.
        """
        sql = sa.text(
            "UPDATE proposals SET status = :status, reviewed_at = :reviewed_at, "
            "review_note = :review_note WHERE id = :id"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(
                sql,
                {
                    "id": proposal_id,
                    "status": status,
                    "reviewed_at": utcnow().isoformat(),
                    "review_note": review_note,
                },
            )
            await conn.commit()
            return result.rowcount > 0

    async def count_by_status(self) -> dict[str, int]:
        """Count proposals by status."""
        sql = sa.text("SELECT status, COUNT(*) FROM proposals GROUP BY status")
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql)
            rows = result.fetchall()
            return {row[0]: row[1] for row in rows}

    async def prune_expired(self, now: datetime | None = None) -> int:
        """Mark expired proposals as 'expired'.

        Returns the number of proposals marked expired.
        """
        if now is None:
            now = utcnow()
        sql = sa.text(
            "UPDATE proposals SET status = 'expired' "
            "WHERE status = 'pending' AND expires_at < :now"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"now": now.isoformat()})
            await conn.commit()
            return result.rowcount or 0

    async def pending_count(self) -> int:
        """Return the number of pending proposals."""
        sql = sa.text("SELECT COUNT(*) FROM proposals WHERE status = 'pending'")
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql)
            return result.scalar() or 0

    def _row_to_proposal(self, row: Any) -> Proposal:
        """Convert a database row to a Proposal."""
        created_at = row.created_at
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        expires_at = row.expires_at
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        reviewed_at = row.reviewed_at
        if isinstance(reviewed_at, str):
            reviewed_at = datetime.fromisoformat(reviewed_at)

        return Proposal(
            id=row.id,
            type=row.type,
            summary=row.summary,
            evidence=json.loads(row.evidence) if row.evidence else [],
            action=json.loads(row.action) if row.action else {},
            confidence=row.confidence,
            status=row.status,
            created_at=created_at,
            expires_at=expires_at,
            reviewed_at=reviewed_at,
            review_note=row.review_note,
        )
