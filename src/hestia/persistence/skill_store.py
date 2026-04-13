"""Skill persistence store."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import sqlalchemy as sa

from hestia.core.clock import utcnow
from hestia.errors import PersistenceError
from hestia.persistence.db import Database
from hestia.persistence.schema import skills
from hestia.skills.state import SkillState


@dataclass
class SkillRecord:
    """A skill record from the database."""

    id: str
    name: str
    description: str
    file_path: str
    state: SkillState
    capabilities: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=utcnow)
    last_run_at: datetime | None = None
    run_count: int = 0
    failure_count: int = 0


class SkillStore:
    """Store for skill definitions and lifecycle state."""

    def __init__(self, db: Database) -> None:
        """Initialize with database connection.

        Args:
            db: Database instance
        """
        self._db = db

    async def create_table(self) -> None:
        """Create the skills table if it doesn't exist.

        Note: In production, use Alembic migrations. This is for testing
        and development convenience.
        """
        # Table is created by metadata.create_all() in Database.create_tables()
        pass

    async def upsert(self, record: SkillRecord) -> SkillRecord:
        """Insert or update a skill record.

        Args:
            record: Skill record to save

        Returns:
            The saved record

        Raises:
            PersistenceError: If database operation fails
        """
        try:
            async with self._db.engine.begin() as conn:
                # Try update first
                result = await conn.execute(
                    sa.update(skills)
                    .where(skills.c.name == record.name)
                    .values(
                        description=record.description,
                        file_path=record.file_path,
                        state=record.state.value,
                        capabilities=json.dumps(record.capabilities),
                        required_tools=json.dumps(record.required_tools),
                        last_run_at=record.last_run_at,
                        run_count=record.run_count,
                        failure_count=record.failure_count,
                    )
                )
                if result.rowcount == 0:
                    # Insert new
                    await conn.execute(
                        sa.insert(skills).values(
                            id=record.id,
                            name=record.name,
                            description=record.description,
                            file_path=record.file_path,
                            state=record.state.value,
                            capabilities=json.dumps(record.capabilities),
                            required_tools=json.dumps(record.required_tools),
                            created_at=record.created_at,
                            last_run_at=record.last_run_at,
                            run_count=record.run_count,
                            failure_count=record.failure_count,
                        )
                    )
            return record
        except Exception as e:
            raise PersistenceError(f"Failed to upsert skill: {e}") from e

    async def get_by_name(self, name: str) -> SkillRecord | None:
        """Get a skill by name.

        Args:
            name: Skill name

        Returns:
            Skill record or None if not found

        Raises:
            PersistenceError: If database operation fails
        """
        try:
            async with self._db.engine.connect() as conn:
                result = await conn.execute(
                    sa.select(skills).where(skills.c.name == name)
                )
                row = result.mappings().first()
                if row is None:
                    return None
                return self._row_to_record(row)
        except Exception as e:
            raise PersistenceError(f"Failed to get skill: {e}") from e

    async def list_all(
        self,
        state: SkillState | None = None,
        exclude_disabled: bool = False,
    ) -> list[SkillRecord]:
        """List all skills.

        Args:
            state: Filter by state (optional)
            exclude_disabled: If True, exclude disabled skills

        Returns:
            List of skill records

        Raises:
            PersistenceError: If database operation fails
        """
        try:
            async with self._db.engine.connect() as conn:
                query = sa.select(skills)
                if state is not None:
                    query = query.where(skills.c.state == state.value)
                if exclude_disabled:
                    query = query.where(skills.c.state != SkillState.DISABLED.value)
                query = query.order_by(skills.c.name)
                result = await conn.execute(query)
                return [self._row_to_record(row) for row in result.mappings()]
        except Exception as e:
            raise PersistenceError(f"Failed to list skills: {e}") from e

    async def update_state(self, name: str, new_state: SkillState) -> bool:
        """Update a skill's state.

        Args:
            name: Skill name
            new_state: New state to set

        Returns:
            True if skill was found and updated

        Raises:
            PersistenceError: If database operation fails
        """
        try:
            async with self._db.engine.begin() as conn:
                result = await conn.execute(
                    sa.update(skills)
                    .where(skills.c.name == name)
                    .values(state=new_state.value)
                )
                return result.rowcount > 0
        except Exception as e:
            raise PersistenceError(f"Failed to update skill state: {e}") from e

    async def record_run(
        self,
        name: str,
        failed: bool = False,
    ) -> bool:
        """Record a skill execution.

        Args:
            name: Skill name
            failed: Whether the execution failed

        Returns:
            True if skill was found and updated

        Raises:
            PersistenceError: If database operation fails
        """
        try:
            async with self._db.engine.begin() as conn:
                # Get current values
                result = await conn.execute(
                    sa.select(
                        skills.c.run_count,
                        skills.c.failure_count,
                    ).where(skills.c.name == name)
                )
                row = result.first()
                if row is None:
                    return False

                run_count = row.run_count + 1
                failure_count = row.failure_count + (1 if failed else 0)

                await conn.execute(
                    sa.update(skills)
                    .where(skills.c.name == name)
                    .values(
                        run_count=run_count,
                        failure_count=failure_count,
                        last_run_at=utcnow(),
                    )
                )
                return True
        except Exception as e:
            raise PersistenceError(f"Failed to record skill run: {e}") from e

    async def delete(self, name: str) -> bool:
        """Delete a skill.

        Args:
            name: Skill name

        Returns:
            True if skill was found and deleted

        Raises:
            PersistenceError: If database operation fails
        """
        try:
            async with self._db.engine.begin() as conn:
                result = await conn.execute(
                    sa.delete(skills).where(skills.c.name == name)
                )
                return result.rowcount > 0
        except Exception as e:
            raise PersistenceError(f"Failed to delete skill: {e}") from e

    def _row_to_record(self, row: Any) -> SkillRecord:
        """Convert a database row to a SkillRecord."""
        return SkillRecord(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            file_path=row["file_path"],
            state=SkillState(row["state"]),
            capabilities=json.loads(row["capabilities"]),
            required_tools=json.loads(row["required_tools"]),
            created_at=row["created_at"],
            last_run_at=row["last_run_at"],
            run_count=row["run_count"],
            failure_count=row["failure_count"],
        )
