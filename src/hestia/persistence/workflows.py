"""Workflow persistence layer for storing workflow definitions and versions."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa

from hestia.core.clock import utcnow
from hestia.persistence.db import Database
from hestia.persistence.schema import workflow_versions, workflows


@dataclass
class Workflow:
    """A workflow with metadata and an active version reference."""

    id: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    active_version: int | None


@dataclass
class WorkflowVersion:
    """A versioned snapshot of a workflow definition."""

    id: str
    workflow_id: str
    version: int
    definition: dict[str, Any]
    created_at: datetime
    is_active: bool


class WorkflowStore:
    """Store for workflow CRUD and version management."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create_table(self) -> None:
        """Deprecated no-op kept for call-site compatibility.

        Schema creation now lives in
        :meth:`hestia.persistence.db.Database.create_tables` via the shared
        SQLAlchemy metadata.
        """
        return None

    async def list_workflows(self) -> list[Workflow]:
        """List all workflows ordered by creation time."""
        query = sa.select(workflows).order_by(workflows.c.created_at.desc())
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return [self._row_to_workflow(row) for row in rows]

    async def create_workflow(
        self,
        name: str,
        description: str | None = None,
        definition: dict[str, Any] | None = None,
    ) -> Workflow:
        """Create a new workflow with an initial version (version 1, active)."""
        workflow_id = str(uuid.uuid4())
        now = utcnow()
        insert = sa.insert(workflows).values(
            id=workflow_id,
            name=name,
            description=description,
            created_at=now,
            updated_at=now,
            active_version=1,
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(insert)
            await conn.commit()

        if definition is not None:
            await self.create_version(workflow_id, definition, is_active=True)

        return Workflow(
            id=workflow_id,
            name=name,
            description=description,
            created_at=now,
            updated_at=now,
            active_version=1,
        )

    async def get_workflow(self, workflow_id: str) -> Workflow | None:
        """Get a workflow by ID."""
        query = sa.select(workflows).where(workflows.c.id == workflow_id)
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            row = result.fetchone()
            if row:
                return self._row_to_workflow(row)
            return None

    async def update_workflow(
        self,
        workflow_id: str,
        name: str | None = None,
        description: str | None = None,
    ) -> Workflow | None:
        """Update workflow metadata."""
        values: dict[str, Any] = {"updated_at": utcnow()}
        if name is not None:
            values["name"] = name
        if description is not None:
            values["description"] = description

        update = (
            sa.update(workflows).where(workflows.c.id == workflow_id).values(**values)
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(update)
            await conn.commit()
            if result.rowcount == 0:
                return None

        query = sa.select(workflows).where(workflows.c.id == workflow_id)
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            row = result.fetchone()
            if row:
                return self._row_to_workflow(row)
            return None

    async def delete_workflow(self, workflow_id: str) -> bool:
        """Delete a workflow and all its versions."""
        async with self._db.engine.connect() as conn:
            # Versions are deleted via CASCADE
            delete = sa.delete(workflows).where(workflows.c.id == workflow_id)
            result = await conn.execute(delete)
            await conn.commit()
            return result.rowcount > 0

    async def list_versions(self, workflow_id: str) -> list[WorkflowVersion]:
        """List all versions for a workflow ordered by version number."""
        query = (
            sa.select(workflow_versions)
            .where(workflow_versions.c.workflow_id == workflow_id)
            .order_by(workflow_versions.c.version.asc())
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return [self._row_to_version(row) for row in rows]

    async def create_version(
        self,
        workflow_id: str,
        definition: dict[str, Any],
        is_active: bool = False,
    ) -> WorkflowVersion:
        """Save a new version for a workflow."""
        # Get next version number
        query = sa.select(sa.func.max(workflow_versions.c.version)).where(
            workflow_versions.c.workflow_id == workflow_id
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            max_version = result.scalar_one() or 0

        version_num = max_version + 1
        version_id = str(uuid.uuid4())
        now = utcnow()

        insert = sa.insert(workflow_versions).values(
            id=version_id,
            workflow_id=workflow_id,
            version=version_num,
            definition=json.dumps(definition),
            created_at=now,
            is_active=is_active,
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(insert)
            await conn.commit()

        if is_active:
            await self._set_active_version(workflow_id, version_num)

        return WorkflowVersion(
            id=version_id,
            workflow_id=workflow_id,
            version=version_num,
            definition=definition,
            created_at=now,
            is_active=is_active,
        )

    async def activate_version(self, workflow_id: str, version: int) -> bool:
        """Activate a specific version of a workflow."""
        # Verify version exists
        query = (
            sa.select(workflow_versions)
            .where(
                sa.and_(
                    workflow_versions.c.workflow_id == workflow_id,
                    workflow_versions.c.version == version,
                )
            )
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            row = result.fetchone()
            if row is None:
                return False

        await self._set_active_version(workflow_id, version)
        return True

    async def get_active_version(self, workflow_id: str) -> WorkflowVersion | None:
        """Get the currently active version for a workflow."""
        # Get active version number from workflow
        wf_query = sa.select(workflows).where(workflows.c.id == workflow_id)
        async with self._db.engine.connect() as conn:
            result = await conn.execute(wf_query)
            wf_row = result.fetchone()
            if wf_row is None or wf_row.active_version is None:
                return None

        version_query = (
            sa.select(workflow_versions)
            .where(
                sa.and_(
                    workflow_versions.c.workflow_id == workflow_id,
                    workflow_versions.c.version == wf_row.active_version,
                )
            )
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(version_query)
            row = result.fetchone()
            if row:
                return self._row_to_version(row)
            return None

    async def _set_active_version(self, workflow_id: str, version: int) -> None:
        """Update the active_version on the workflow and clear old active flags."""
        now = utcnow()
        async with self._db.engine.connect() as conn:
            # Clear all active flags for this workflow
            clear = (
                sa.update(workflow_versions)
                .where(workflow_versions.c.workflow_id == workflow_id)
                .values(is_active=False)
            )
            await conn.execute(clear)

            # Set the new active flag
            set_active = (
                sa.update(workflow_versions)
                .where(
                    sa.and_(
                        workflow_versions.c.workflow_id == workflow_id,
                        workflow_versions.c.version == version,
                    )
                )
                .values(is_active=True)
            )
            await conn.execute(set_active)

            # Update workflow active_version
            update_wf = (
                sa.update(workflows)
                .where(workflows.c.id == workflow_id)
                .values(active_version=version, updated_at=now)
            )
            await conn.execute(update_wf)
            await conn.commit()

    def _row_to_workflow(self, row: Any) -> Workflow:
        """Convert a database row to a Workflow."""
        created_at = row.created_at
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        updated_at = row.updated_at
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        return Workflow(
            id=row.id,
            name=row.name,
            description=row.description,
            created_at=created_at,
            updated_at=updated_at,
            active_version=row.active_version,
        )

    def _row_to_version(self, row: Any) -> WorkflowVersion:
        """Convert a database row to a WorkflowVersion."""
        created_at = row.created_at
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        definition = json.loads(row.definition) if row.definition else {}
        return WorkflowVersion(
            id=row.id,
            workflow_id=row.workflow_id,
            version=row.version,
            definition=definition,
            created_at=created_at,
            is_active=bool(row.is_active),
        )
