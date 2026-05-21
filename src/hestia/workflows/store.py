"""Workflow persistence layer."""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa

from hestia.core.clock import utcnow
from hestia.errors import PersistenceError
from hestia.persistence.db import Database
from hestia.persistence.schema import workflow_versions, workflows

from .models import Workflow, WorkflowEdge, WorkflowNode, WorkflowVersion


class WorkflowStore:
    """Typed CRUD wrapper for workflow persistence."""

    def __init__(self, db: Database) -> None:
        """Initialize with a Database instance."""
        self._db = db

    async def create_tables(self) -> None:
        """Create workflow tables if they do not already exist."""
        if self._db.engine is None:
            raise PersistenceError("Database not connected. Call connect() first.")
        async with self._db.engine.begin() as conn:
            await conn.run_sync(workflows.create, checkfirst=True)
            await conn.run_sync(workflow_versions.create, checkfirst=True)

    # --- Workflow CRUD ---

    async def _upsert(
        self,
        table: Any,
        values: dict[str, Any],
        conflict_keys: list[str],
        update_keys: list[str],
    ) -> None:
        """Dialect-aware upsert helper.

        Supports SQLite and PostgreSQL via ON CONFLICT. Falls back to
        select-then-insert/update for other dialects.
        """
        async with self._db.engine.connect() as conn:
            stmt: Any
            if conn.dialect.name == "sqlite":
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert

                sqlite_stmt = sqlite_insert(table).values(**values)
                stmt = sqlite_stmt.on_conflict_do_update(
                    index_elements=conflict_keys,
                    set_={k: values[k] for k in update_keys},
                )
            elif conn.dialect.name == "postgresql":
                from sqlalchemy.dialects.postgresql import insert as pg_insert

                pg_stmt = pg_insert(table).values(**values)
                stmt = pg_stmt.on_conflict_do_update(
                    index_elements=conflict_keys,
                    set_={k: values[k] for k in update_keys},
                )
            else:
                where_clause = sa.and_(
                    *(table.c[k] == values[k] for k in conflict_keys)
                )
                result = await conn.execute(sa.select(table).where(where_clause))
                if result.fetchone() is not None:
                    await conn.execute(
                        sa.update(table).where(where_clause).values(**values)
                    )
                else:
                    await conn.execute(sa.insert(table).values(**values))
                await conn.commit()
                return

            await conn.execute(stmt)
            await conn.commit()

    async def save_workflow(self, workflow: Workflow) -> Workflow:
        """Insert or update a workflow."""
        now = utcnow()
        if workflow.created_at is None:
            workflow.created_at = now
        workflow.updated_at = now

        values: dict[str, Any] = {
            "id": workflow.id,
            "name": workflow.name,
            "description": workflow.description,
            "trigger_type": workflow.trigger_type,
            "trigger_config": json.dumps(workflow.trigger_config),
            "owner_id": workflow.owner_id,
            "trust_level": workflow.trust_level,
            "created_at": workflow.created_at,
            "updated_at": workflow.updated_at,
        }

        await self._upsert(
            workflows,
            values,
            conflict_keys=["id"],
            update_keys=[
                "name",
                "description",
                "trigger_type",
                "trigger_config",
                "owner_id",
                "trust_level",
                "updated_at",
            ],
        )
        return workflow

    async def get_workflow(self, workflow_id: str) -> Workflow | None:
        """Get a workflow by ID."""
        query = sa.select(workflows).where(workflows.c.id == workflow_id)
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            row = result.fetchone()
            if row is None:
                return None
            return self._row_to_workflow(row)

    async def list_workflows(self) -> list[Workflow]:
        """List all workflows ordered by name."""
        query = sa.select(workflows).order_by(workflows.c.name)
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return [self._row_to_workflow(row) for row in rows]

    async def delete_workflow(self, workflow_id: str) -> bool:
        """Delete a workflow and all its versions."""
        async with self._db.engine.connect() as conn:
            # Versions are deleted by FK cascade (if supported) or manually
            await conn.execute(
                sa.delete(workflow_versions).where(
                    workflow_versions.c.workflow_id == workflow_id
                )
            )
            result = await conn.execute(
                sa.delete(workflows).where(workflows.c.id == workflow_id)
            )
            await conn.commit()
            return result.rowcount > 0

    # --- Version CRUD ---

    async def save_version(self, version: WorkflowVersion) -> WorkflowVersion:
        """Insert or update a workflow version."""
        if version.created_at is None:
            version.created_at = utcnow()

        nodes_json = json.dumps(
            [
                {
                    "id": n.id,
                    "type": n.type,
                    "label": n.label,
                    "config": n.config,
                    "position": n.position,
                    "capabilities": n.capabilities,
                }
                for n in version.nodes
            ]
        )
        edges_json = json.dumps(
            [
                {
                    "id": e.id,
                    "source_node_id": e.source_node_id,
                    "target_node_id": e.target_node_id,
                    "source_handle": e.source_handle,
                    "target_handle": e.target_handle,
                    "condition": e.condition,
                }
                for e in version.edges
            ]
        )

        values: dict[str, Any] = {
            "workflow_id": version.workflow_id,
            "version": version.version,
            "nodes": nodes_json,
            "edges": edges_json,
            "created_at": version.created_at,
            "is_active": version.is_active,
        }

        await self._upsert(
            workflow_versions,
            values,
            conflict_keys=["workflow_id", "version"],
            update_keys=["nodes", "edges", "is_active"],
        )
        return version

    async def get_active_version(self, workflow_id: str) -> WorkflowVersion | None:
        """Get the active version for a workflow."""
        query = (
            sa.select(workflow_versions)
            .where(
                sa.and_(
                    workflow_versions.c.workflow_id == workflow_id,
                    workflow_versions.c.is_active.is_(True),
                )
            )
            .order_by(workflow_versions.c.version.desc())
            .limit(1)
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            row = result.fetchone()
            if row is None:
                return None
            return self._row_to_version(row)

    async def get_active_versions_batch(
        self, workflow_ids: list[str]
    ) -> dict[str, WorkflowVersion | None]:
        """Fetch the active version for multiple workflows in a single query."""
        if not workflow_ids:
            return {}

        # Use a subquery to pick the highest active version per workflow
        subq = (
            sa.select(
                workflow_versions.c.workflow_id,
                sa.func.max(workflow_versions.c.version).label("max_version"),
            )
            .where(
                sa.and_(
                    workflow_versions.c.workflow_id.in_(workflow_ids),
                    workflow_versions.c.is_active.is_(True),
                )
            )
            .group_by(workflow_versions.c.workflow_id)
            .subquery()
        )

        query = sa.select(workflow_versions).join(
            subq,
            sa.and_(
                workflow_versions.c.workflow_id == subq.c.workflow_id,
                workflow_versions.c.version == subq.c.max_version,
            ),
        )

        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()

        version_map: dict[str, WorkflowVersion | None] = dict.fromkeys(workflow_ids, None)
        for row in rows:
            version_map[row.workflow_id] = self._row_to_version(row)
        return version_map

    async def list_versions(self, workflow_id: str) -> list[WorkflowVersion]:
        """List all versions for a workflow, newest first."""
        query = (
            sa.select(workflow_versions)
            .where(workflow_versions.c.workflow_id == workflow_id)
            .order_by(workflow_versions.c.version.desc())
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return [self._row_to_version(row) for row in rows]

    async def activate_version(self, workflow_id: str, version: int) -> bool:
        """Activate a specific version, deactivating all others for the workflow.

        Returns True if the version was found and activated.
        """
        async with self._db.engine.connect() as conn:
            # Verify the version exists
            result = await conn.execute(
                sa.select(workflow_versions)
                .where(
                    sa.and_(
                        workflow_versions.c.workflow_id == workflow_id,
                        workflow_versions.c.version == version,
                    )
                )
            )
            if result.fetchone() is None:
                await conn.rollback()
                return False

            # Deactivate all versions for this workflow
            await conn.execute(
                sa.update(workflow_versions)
                .where(workflow_versions.c.workflow_id == workflow_id)
                .values(is_active=False)
            )

            # Activate the target version
            await conn.execute(
                sa.update(workflow_versions)
                .where(
                    sa.and_(
                        workflow_versions.c.workflow_id == workflow_id,
                        workflow_versions.c.version == version,
                    )
                )
                .values(is_active=True)
            )
            await conn.commit()
            return True

    # --- Row converters ---

    def _row_to_workflow(self, row: Any) -> Workflow:
        """Convert a database row to a Workflow."""
        trigger_config = {}
        if row.trigger_config:
            try:
                trigger_config = json.loads(row.trigger_config)
            except json.JSONDecodeError:
                trigger_config = {}
        return Workflow(
            id=row.id,
            name=row.name,
            description=row.description or "",
            trigger_type=row.trigger_type or "manual",
            trigger_config=trigger_config,
            owner_id=getattr(row, "owner_id", "") or "",
            trust_level=getattr(row, "trust_level", "paranoid") or "paranoid",
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _row_to_version(self, row: Any) -> WorkflowVersion:
        """Convert a database row to a WorkflowVersion."""
        nodes: list[WorkflowNode] = []
        if row.nodes:
            try:
                nodes = [
                    WorkflowNode(
                        id=n["id"],
                        type=n["type"],
                        label=n["label"],
                        config=n.get("config", {}),
                        position=n.get("position", {}),
                        capabilities=n.get("capabilities", []),
                    )
                    for n in json.loads(row.nodes)
                ]
            except (json.JSONDecodeError, KeyError, TypeError):
                nodes = []

        edges: list[WorkflowEdge] = []
        if row.edges:
            try:
                edges = [
                    WorkflowEdge(
                        id=e["id"],
                        source_node_id=e["source_node_id"],
                        target_node_id=e["target_node_id"],
                        source_handle=e.get("source_handle"),
                        target_handle=e.get("target_handle"),
                        condition=e.get("condition"),
                    )
                    for e in json.loads(row.edges)
                ]
            except (json.JSONDecodeError, KeyError, TypeError):
                edges = []

        return WorkflowVersion(
            workflow_id=row.workflow_id,
            version=row.version,
            nodes=nodes,
            edges=edges,
            created_at=row.created_at,
            is_active=bool(row.is_active) if row.is_active is not None else False,
        )
