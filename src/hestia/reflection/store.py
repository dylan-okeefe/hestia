"""Proposal storage using raw SQLite DDL."""
from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa

from hestia.core.clock import utcnow
from hestia.reflection.types import Proposal, ProposalStatus

if TYPE_CHECKING:
    from hestia.persistence.db import Database


def _dt(value: Any) -> datetime:
    return datetime.fromisoformat(value) if isinstance(value, str) else value


def _dt_opt(value: Any) -> datetime | None:
    return datetime.fromisoformat(value) if isinstance(value, str) else value


class ProposalStore:
    """Typed CRUD wrapper for proposal persistence."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create_table(self) -> None:
        ddl = "CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, type TEXT NOT NULL, summary TEXT NOT NULL, evidence TEXT NOT NULL, action TEXT NOT NULL, confidence REAL NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL, expires_at TEXT NOT NULL, reviewed_at TEXT, review_note TEXT)"  # noqa: E501
        async with self._db.engine.connect() as conn:
            await conn.execute(sa.text(ddl))
            for idx in ("CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status, created_at)", "CREATE INDEX IF NOT EXISTS idx_proposals_expires ON proposals(expires_at)"):  # noqa: E501
                await conn.execute(sa.text(idx))
            await conn.commit()

    async def save(self, proposal: Proposal) -> None:
        sql = sa.text("INSERT INTO proposals (id, type, summary, evidence, action, confidence, status, created_at, expires_at, reviewed_at, review_note) VALUES (:id, :type, :summary, :evidence, :action, :confidence, :status, :created_at, :expires_at, :reviewed_at, :review_note)")  # noqa: E501
        async with self._db.engine.connect() as conn:
            await conn.execute(sql, {
                "id": proposal.id, "type": proposal.type, "summary": proposal.summary,
                "evidence": json.dumps(proposal.evidence), "action": json.dumps(proposal.action),
                "confidence": proposal.confidence, "status": proposal.status,
                "created_at": proposal.created_at.isoformat(), "expires_at": proposal.expires_at.isoformat(),  # noqa: E501
                "reviewed_at": proposal.reviewed_at.isoformat() if proposal.reviewed_at else None,
                "review_note": proposal.review_note,
            })
            await conn.commit()

    async def get(self, proposal_id: str) -> Proposal | None:
        sql = sa.text("SELECT * FROM proposals WHERE id = :id")
        async with self._db.engine.connect() as conn:
            row = (await conn.execute(sql, {"id": proposal_id})).fetchone()
            return self._row_to_proposal(row) if row else None

    async def list_by_status(self, status: ProposalStatus | None = None, limit: int = 100) -> list[Proposal]:  # noqa: E501
        if status:
            sql = sa.text("SELECT * FROM proposals WHERE status = :status ORDER BY created_at DESC LIMIT :limit")  # noqa: E501
            params = {"status": status, "limit": limit}
        else:
            sql = sa.text("SELECT * FROM proposals ORDER BY created_at DESC LIMIT :limit")
            params = {"limit": limit}
        async with self._db.engine.connect() as conn:
            return [self._row_to_proposal(r) for r in (await conn.execute(sql, params)).fetchall()]

    async def update_status(self, proposal_id: str, status: ProposalStatus, review_note: str | None = None) -> bool:  # noqa: E501
        sql = sa.text("UPDATE proposals SET status = :status, reviewed_at = :reviewed_at, review_note = :review_note WHERE id = :id")  # noqa: E501
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"id": proposal_id, "status": status, "reviewed_at": utcnow().isoformat(), "review_note": review_note})  # noqa: E501
            await conn.commit()
            return result.rowcount > 0

    async def count_by_status(self) -> dict[str, int]:
        sql = sa.text("SELECT status, COUNT(*) FROM proposals GROUP BY status")
        async with self._db.engine.connect() as conn:
            return {r[0]: r[1] for r in (await conn.execute(sql)).fetchall()}

    async def prune_expired(self, now: datetime | None = None) -> int:
        if now is None:
            now = utcnow()
        sql = sa.text("UPDATE proposals SET status = 'expired' WHERE status = 'pending' AND expires_at < :now")  # noqa: E501
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"now": now.isoformat()})
            await conn.commit()
            return result.rowcount or 0

    async def pending_count(self) -> int:
        sql = sa.text("SELECT COUNT(*) FROM proposals WHERE status = 'pending'")
        async with self._db.engine.connect() as conn:
            return (await conn.execute(sql)).scalar() or 0

    def _row_to_proposal(self, row: Any) -> Proposal:
        return Proposal(
            id=row.id, type=row.type, summary=row.summary,
            evidence=json.loads(row.evidence) if row.evidence else [],
            action=json.loads(row.action) if row.action else {},
            confidence=row.confidence, status=row.status,
            created_at=_dt(row.created_at), expires_at=_dt(row.expires_at),
            reviewed_at=_dt_opt(row.reviewed_at), review_note=row.review_note,
        )
