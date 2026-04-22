# ADR-004: Persistence is SQLAlchemy Core async with SQLite default, Postgres via URL override

- **Status:** Accepted
- **Date:** 2026-04-09
- **Context:** We need durable state (sessions, messages, turns) that survives
  restarts. SQLite is perfect for single-node deployment (zero config, single file).
  However, we may want to run the database on a different machine from the agent
  host in future (e.g., for backup or multi-agent scenarios).
- **Decision:** Use SQLAlchemy Core (not ORM) with async drivers. Default to
  `sqlite+aiosqlite://`, but allow `postgresql+asyncpg://` via config URL change.
  Artifact bytes always stay on the agent host's disk regardless of DB backend.
- **Consequences:** Must write explicit SQL queries, no lazy loading. Schema
  migrations via Alembic. If using remote Postgres, large file reads/writes must
  go through the artifact store, not the DB connection.
