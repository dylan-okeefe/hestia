# Database Migrations

This directory contains alembic migrations for Hestia's database schema.

## FTS5 Virtual Tables

SQLite FTS5 virtual tables (specifically the `memory` table) are **not**
managed by alembic. SQLAlchemy's `Table`/`MetaData` API does not support
virtual tables, so alembic cannot generate or apply DDL for them.

The `memory` FTS5 virtual table is created and migrated at runtime by
`MemoryStore.create_table()` in `src/hestia/memory/store.py`. This method
handles schema detection, backup/restore migration for old schemas, and
fallback to regular tables when FTS5 is unavailable.
