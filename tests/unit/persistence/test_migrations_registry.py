"""Migration registry integrity tests.

Process finding from the audit-remediation-r1 review: m010 existed as a
function but was never appended to MIGRATIONS, and the full green gate
suite sailed through. These tests make that class of failure loud.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection  # noqa: F401

import hestia.persistence.migrations as migrations_module
from hestia.persistence.migrations import MIGRATIONS


def _defined_migration_functions() -> list[str]:
    """Every module-level function named like a migration (m###_*)."""
    return sorted(
        name
        for name, obj in vars(migrations_module).items()
        if re.fullmatch(r"m\d{3}_\w+", name) and callable(obj)
    )


def test_every_defined_migration_is_registered() -> None:
    defined = _defined_migration_functions()
    registered = [m.__name__ for m in MIGRATIONS]
    assert registered == defined, (
        "MIGRATIONS does not match the set of defined migrations. "
        f"Missing from registry: {sorted(set(defined) - set(registered))}. "
        f"In registry but not defined: {sorted(set(registered) - set(defined))}."
    )


def test_migrations_are_ordered_with_no_duplicates() -> None:
    numbers = [int(re.match(r"m(\d{3})_", m.__name__).group(1)) for m in MIGRATIONS]
    assert numbers == sorted(numbers), "MIGRATIONS out of numeric order"
    assert len(set(numbers)) == len(numbers), "duplicate migration number"


@pytest.mark.asyncio
async def test_migration_chain_runs_clean_on_fresh_db(tmp_path) -> None:
    """Smoke: the full chain applies to a fresh database, twice."""
    import sqlalchemy as sa

    from hestia.persistence.db import Database

    db = Database(f"sqlite+aiosqlite:///{tmp_path}/fresh.db")
    await db.connect()
    try:
        await db.create_tables()
        # Idempotency: a second full run must succeed unchanged.
        await db.create_tables()

        async with db.engine.connect() as conn:
            for table, column in [
                ("messages", "correction"),
                ("workflows", "allow_listed_tools"),
                ("scheduled_tasks", "task_type"),
                ("workflow_executions", "is_test"),
            ]:
                result = await conn.execute(
                    sa.text(
                        "SELECT name FROM pragma_table_info(:t) WHERE name = :c"
                    ),
                    {"t": table, "c": column},
                )
                assert result.fetchone() is not None, f"{table}.{column} missing"

            indexes = {
                row[0]
                for row in await conn.execute(
                    sa.text(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='index' AND name LIKE 'idx_%'"
                    )
                )
            }
            assert "idx_messages_session_idx" in indexes
            assert "idx_sessions_last_active" in indexes
    finally:
        await db.close()
