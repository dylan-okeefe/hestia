# ADR-0032: Typed failure bundles

- **Status:** Accepted
- **Date:** 2026-04-10
- **Context:** Failed turns stored only a string on the turn row; no stable
  classification for dashboards, alerts, or future failure analysis.

- **Decision:**
  1. Introduce `FailureClass` enum and `classify_error()` mapping from
     `HestiaError` subclasses (plus string heuristics for generic exceptions).
  2. Persist `failure_bundles` rows (session, turn, class, severity, message,
     tool chain JSON, timestamp) via `FailureStore`, optionally wired on the
     orchestrator.
  3. Table is defined in SQLAlchemy `schema.py` and upgraded via Alembic for
     existing databases.

- **Consequences:** Foundation for CLI/scheduler reporting and future
  postmortem tooling without changing the hot-path turn state machine.
