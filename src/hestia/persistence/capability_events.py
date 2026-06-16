"""Audit persistence for capability-gate decisions."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa

from hestia.core.clock import utcnow

if TYPE_CHECKING:
    from hestia.persistence.db import Database
    from hestia.policy.gate import CapabilityRequest, CapabilityResult


_SENSITIVE_KEYS = frozenset({
    "secret",
    "password",
    "token",
    "authorization",
    "api_key",
    "apikey",
})


def _scrub_value(key: str, value: Any) -> Any:
    """Redact values whose key suggests a credential."""
    key_lower = key.lower()
    if any(sensitive in key_lower for sensitive in _SENSITIVE_KEYS):
        return "***"
    if isinstance(value, dict):
        return {k: _scrub_value(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_value(key, item) for item in value]
    return value


def scrub_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of tool inputs with likely secrets redacted."""
    return {key: _scrub_value(key, value) for key, value in inputs.items()}


@dataclass
class CapabilityEvent:
    """Structured audit record emitted by ``CapabilityGate``."""

    id: str
    tool_name: str
    arguments_json: str
    channel: str
    actor_platform: str
    actor_platform_user: str
    source_workflow_id: str | None
    source_trigger_id: str | None
    decision: str
    reason: str
    injection_flagged: bool
    created_at: datetime


class CapabilityEventStore:
    """Store structured capability-gate audit events."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def record(
        self,
        request: CapabilityRequest,
        result: CapabilityResult,
        *,
        injection_flagged: bool = False,
    ) -> None:
        """Persist a gate decision.

        Arguments are scrubbed before storage to avoid leaking secrets into
        the audit log.
        """
        from hestia.policy.gate import CapabilityRequest, CapabilityResult

        if not isinstance(request, CapabilityRequest) or not isinstance(result, CapabilityResult):
            raise TypeError("request and result must be CapabilityRequest/CapabilityResult")

        decision = "escalated" if result.requires_confirmation else ("allowed" if result.allowed else "denied")
        sql = sa.text(
            "INSERT INTO capability_events ("
            "id, tool_name, arguments_json, channel, actor_platform, actor_platform_user, "
            "source_workflow_id, source_trigger_id, decision, reason, injection_flagged, created_at"
            ") VALUES ("
            ":id, :tool_name, :arguments_json, :channel, :actor_platform, :actor_platform_user, "
            ":source_workflow_id, :source_trigger_id, :decision, :reason, :injection_flagged, :created_at"
            ")"
        )
        now = utcnow()
        params: dict[str, Any] = {
            "id": uuid.uuid4().hex,
            "tool_name": request.tool_name,
            "arguments_json": json.dumps(scrub_inputs(request.inputs), default=str),
            "channel": request.channel.value,
            "actor_platform": request.actor.platform,
            "actor_platform_user": request.actor.platform_user,
            "source_workflow_id": request.source_workflow_id,
            "source_trigger_id": request.source_trigger_id,
            "decision": decision,
            "reason": result.reason,
            "injection_flagged": 1 if injection_flagged else 0,
            "created_at": now.isoformat(),
        }
        async with self._db.engine.connect() as conn:
            await conn.execute(sql, params)
            await conn.commit()

    async def list_recent(self, limit: int = 100) -> list[CapabilityEvent]:
        """Return recent events ordered newest first."""
        sql = sa.text(
            "SELECT id, tool_name, arguments_json, channel, actor_platform, actor_platform_user, "
            "source_workflow_id, source_trigger_id, decision, reason, injection_flagged, created_at "
            "FROM capability_events ORDER BY created_at DESC LIMIT :limit"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"limit": limit})
            rows = result.fetchall()
        return [self._row_to_event(row) for row in rows]

    def _row_to_event(self, row: Any) -> CapabilityEvent:
        created_at = row.created_at
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        return CapabilityEvent(
            id=row.id,
            tool_name=row.tool_name,
            arguments_json=row.arguments_json,
            channel=row.channel,
            actor_platform=row.actor_platform,
            actor_platform_user=row.actor_platform_user,
            source_workflow_id=row.source_workflow_id,
            source_trigger_id=row.source_trigger_id,
            decision=row.decision,
            reason=row.reason,
            injection_flagged=bool(row.injection_flagged),
            created_at=created_at,
        )
