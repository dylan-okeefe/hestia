"""D8 (narrow): every table Alembic creates must exist in the bootstrap
metadata create_all actually builds. Production never runs Alembic; a
table that lives only in migrations/versions is a landmine (see skills)."""

from __future__ import annotations

import re
from pathlib import Path

import hestia.persistence.schema as schema

ALEMBIC_VERSIONS = REPO = Path(__file__).resolve().parents[3] / "migrations" / "versions"

# Tables that exist only as historical Alembic migrations and are read by
# nothing in src/. Documented here instead of resurrected in schema.py.
HISTORICAL_ALEMBIC_ONLY = {"skills"}


def _alembic_tables() -> set[str]:
    tables: set[str] = set()
    for path in ALEMBIC_VERSIONS.glob("*.py"):
        tables |= set(re.findall(r'create_table\(\s*["\'](\w+)["\']', path.read_text()))
        tables |= set(re.findall(r'CREATE TABLE (?:IF NOT EXISTS )?(\w+)', path.read_text()))
    return tables


def test_alembic_created_tables_exist_in_bootstrap_metadata() -> None:
    metadata_tables = set(schema.metadata.tables.keys())
    alembic = _alembic_tables() - HISTORICAL_ALEMBIC_ONLY
    missing = sorted(t for t in alembic if t not in metadata_tables)
    assert not missing, (
        f"Alembic creates tables the production bootstrap does not: {missing}. "
        "Add them to persistence/schema.py or list them in "
        "HISTORICAL_ALEMBIC_ONLY with a reason."
    )
